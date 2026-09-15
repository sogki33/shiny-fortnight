"""Reviewed queue publishing, candidate discovery and encrypted token renewal."""
import argparse
import hashlib
import json
import os
import subprocess
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

import requests
from cryptography.fernet import Fernet
from bot import search_products

ROOT = Path(__file__).parent
DATA = ROOT / 'data'
DISCLOSURE = '이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.'
API = 'https://graph.threads.net/v1.0'


def read(name, default):
    path = DATA / name
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def write(name, data):
    DATA.mkdir(exist_ok=True)
    path = DATA / name
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def persist():
    if os.getenv('PERSIST_GIT') != '1':
        return
    for args in [('add', 'data'), ('diff', '--cached', '--quiet')]:
        result = subprocess.run(['git', *args], cwd=ROOT, check=False)
    if result.returncode == 0:
        return
    subprocess.run(['git', 'commit', '-m', 'Update automation state'], cwd=ROOT, check=True)
    subprocess.run(['git', 'push'], cwd=ROOT, check=True)


def token():
    path = DATA / 'threads-token.enc'
    if path.exists():
        return Fernet(os.environ['TOKEN_ENCRYPTION_KEY'].strip().encode()).decrypt(path.read_bytes()).decode()
    return os.environ['THREADS_ACCESS_TOKEN'].strip()


def api(method, path, **params):
    try:
        r = requests.request(method, API + '/' + path,
            headers={'Authorization': 'Bearer ' + token()},
            params=params if method == 'GET' else None,
            data=params if method != 'GET' else None, timeout=45)
        if not r.ok:
            raise RuntimeError('Threads request failed: HTTP ' + str(r.status_code))
        return r.json()
    except requests.RequestException:
        raise RuntimeError('Threads network error; inspect state before retrying.') from None


def identity():
    p = api('GET', 'me', fields='id,username')
    if p.get('username') != 'jamestv1007' or str(p.get('id')) != os.environ['THREADS_USER_ID'].strip():
        raise RuntimeError('Wrong Threads account; no publishing allowed.')
    return str(p['id'])


def validate(item):
    if item.get('status') != 'approved' or not item.get('reviewed_by'):
        raise ValueError('Post needs content review.')
    if not item.get('text') or len(item['text']) > 500:
        raise ValueError('Invalid text length.')
    if item.get('media_type') not in ('IMAGE', 'VIDEO'):
        raise ValueError('A photo or video is required.')
    if urlparse(item.get('media_url', '')).scheme != 'https' or not item.get('media_rights'):
        raise ValueError('Missing media URL or source rights.')
    if item.get('affiliate_url'):
        if urlparse(item['affiliate_url']).hostname != 'link.coupang.com':
            raise ValueError('Unexpected affiliate link host.')
        if DISCLOSURE not in item['text'] or item['affiliate_url'] not in item['text']:
            raise ValueError('Affiliate disclosure missing from main post.')
    return True


def publish(dry_run=False):
    queue = read('queue.json', [])
    ledger = read('publication.json', {})
    # Unknown outcomes require reconciliation; never blindly publish another copy.
    if any(v.get('phase') != 'published' for v in ledger.values()):
        raise RuntimeError('Unresolved previous request. Reconcile publication.json first.')
    selected = next((p for p in queue if p.get('status') == 'approved' and p['id'] not in ledger), None)
    if not selected:
        print('No approved posts available; skipped publishing.')
        return
    validate(selected)
    if selected.get('not_before'):
        due = datetime.fromisoformat(selected['not_before'])
        if due.tzinfo is None:
            raise ValueError('Scheduled time must include timezone.')
        if datetime.now(timezone.utc) < due:
            print('Next post scheduled for:', selected['not_before'])
            return
    if dry_run:
        print('Validated draft:', selected['id'])
        return
    uid = identity()
    entry = {'phase': 'creating', 'at': datetime.now(timezone.utc).isoformat()}
    ledger[selected['id']] = entry
    write('publication.json', ledger)
    persist()
    params = {'media_type': selected['media_type'], 'text': selected['text']}
    params['image_url' if selected['media_type'] == 'IMAGE' else 'video_url'] = selected['media_url']
    container = api('POST', uid + '/threads', **params)['id']
    entry.update(container_id=container, phase='processing')
    write('publication.json', ledger)
    persist()
    for _ in range(24):
        status = api('GET', str(container), fields='status')['status']
        if status == 'FINISHED':
            break
        if status in ('ERROR', 'EXPIRED'):
            raise RuntimeError('Media processing failed: ' + status)
        time.sleep(5)
    else:
        raise RuntimeError('Media processing timed out; no text-only fallback.')
    entry['phase'] = 'publishing'
    write('publication.json', ledger)
    persist()
    post_id = api('POST', uid + '/threads_publish', creation_id=container)['id']
    entry.update(phase='published', post_id=post_id)
    write('publication.json', ledger)
    persist()
    # The link stays in the main post so a comment failure cannot lose attribution.
    print('Published:', selected['id'], post_id)


def discover():
    state = read('discovery.json', {'index': 0})
    topics = ['스팀다리미', '주방 수전 필터', '유리컵', '책상 정리', '접이식 빨래바구니', '무드등']
    topic = topics[state['index'] % len(topics)]
    products = search_products(topic, 5)
    candidates = read('candidates.json', [])
    known = {str(p['productId']) for p in candidates}
    for p in products:
        if str(p.get('productId')) in known or not p.get('productImage') or not p.get('productUrl'):
            continue
        candidates.append({k: p.get(k) for k in ('productId','productName','productPrice','productImage','productUrl','isRocket')})
        known.add(str(p['productId']))
    state['index'] += 1
    state['last_topic'] = topic
    state['checked_at'] = datetime.now(timezone.utc).isoformat()
    write('candidates.json', candidates[-60:])
    write('discovery.json', state)
    persist()
    print('Product candidates updated:', topic, len(products), 'results. Not auto-approved.')


def refresh():
    state = read('token-refresh.json', {})
    now = datetime.now(timezone.utc)
    if state.get('refreshed_at') and now - datetime.fromisoformat(state['refreshed_at']) < timedelta(days=27):
        print('Token renewal not due.')
        return
    identity()
    try:
        r = requests.get('https://graph.threads.net/refresh_access_token', params={
            'grant_type': 'th_refresh_token', 'access_token': token()}, timeout=45)
        if not r.ok:
            raise RuntimeError('Token refresh failed. HTTP ' + str(r.status_code))
        result = r.json()
        encrypted = Fernet(os.environ['TOKEN_ENCRYPTION_KEY'].strip().encode()).encrypt(result['access_token'].encode())
        (DATA / 'threads-token.enc').write_bytes(encrypted)
        write('token-refresh.json', {'refreshed_at': now.isoformat(), 'expires_in': result['expires_in']})
        persist()
        print('Renewed token stored encrypted; no token printed.')
    except requests.RequestException:
        raise RuntimeError('Token renewal network error.') from None


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['discover', 'publish', 'refresh'])
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        {'discover': discover, 'refresh': refresh,
         'publish': lambda: publish(args.dry_run)}[args.command]()
    except Exception as exc:
        print('Automation stopped:', type(exc).__name__, str(exc) if isinstance(exc, (ValueError, RuntimeError)) else 'details withheld')
        raise SystemExit(1)
