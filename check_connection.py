"""Read-only connection check; never publishes or prints credentials."""
import os
import sys
import requests


def main():
    required = ['THREADS_ACCESS_TOKEN', 'THREADS_USER_ID',
                'COUPANG_ACCESS_KEY', 'COUPANG_SECRET_KEY']
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        print('Missing GitHub Secrets: ' + ', '.join(missing))
        return 1
    try:
        response = requests.get(
            'https://graph.threads.net/v1.0/me',
            params={'fields': 'id,username'},
            headers={'Authorization': 'Bearer ' + os.environ['THREADS_ACCESS_TOKEN']},
            timeout=30)
        if response.status_code != 200:
            print('Threads authentication failed. HTTP', response.status_code)
            return 1
        profile = response.json()
        if profile.get('username') != 'jamestv1007':
            print('Threads account mismatch; expected jamestv1007.')
            return 1
        if str(profile.get('id')) != os.environ['THREADS_USER_ID']:
            print('THREADS_USER_ID does not match token owner.')
            return 1
        from bot import coupang_auth, COUPANG_DOMAIN, SEARCH_PATH
        query = 'keyword=kitchen&limit=1'
        response = requests.get(COUPANG_DOMAIN + SEARCH_PATH + '?' + query,
            headers={'Authorization': coupang_auth('GET', SEARCH_PATH, query)}, timeout=30)
        if response.status_code != 200 or response.json().get('rCode') != '0':
            print('Coupang API check failed. HTTP', response.status_code)
            return 1
        print('Threads jamestv1007 and Coupang API connection verified. No post published.')
        return 0
    except (requests.RequestException, ValueError, KeyError):
        print('Connection check failed; credentials and response body omitted from logs.')
        return 1


if __name__ == '__main__':
    sys.exit(main())
