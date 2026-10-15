"""포이즌 리셀 마진 스캐너 - 데스크톱 앱 (tkinter, 추가 설치 없음)."""
import json
import os
import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import ttk, messagebox

import resell as r

WATCHLIST = r.ROOT / 'watchlist.csv'
CONFIG = r.ROOT / 'config.json'
WEBHOOK_FILE = r.ROOT / 'discord_webhook.txt'
FIELDS = ('style_code', 'name', 'size', 'poizon_price')
CFG_LABELS = {'fee_rate': '수수료율 (0.10 = 10%)', 'min_fee': '최소 수수료', 'shipping': '배송비',
              'min_profit': '알림 최소 순이익', 'min_roi': '알림 최소 수익률 (0.05 = 5%)'}


def won(n):
    return f'{int(n):,}'


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('포이즌 리셀 마진 스캐너')
        self.geometry('1000x640')
        nb = ttk.Notebook(self)
        nb.pack(fill='both', expand=True, padx=8, pady=8)
        self.build_scan(nb)
        self.build_watchlist(nb)
        self.build_calc(nb)
        self.build_settings(nb)

    # ---- 스캔 ----
    def build_scan(self, nb):
        f = ttk.Frame(nb, padding=8)
        nb.add(f, text='  스캔  ')
        top = ttk.Frame(f)
        top.pack(fill='x')
        self.scan_btn = ttk.Button(top, text='▶ 스캔 시작', command=self.start_scan)
        self.scan_btn.pack(side='left')
        self.notify_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text='디스코드 알림 보내기', variable=self.notify_var).pack(side='left', padx=12)
        self.status = ttk.Label(top, text='관심 상품 탭에 품번과 포이즌 시세를 넣고 스캔하세요.')
        self.status.pack(side='left', padx=12)
        cols = ('ok', 'style_code', 'size', 'name', 'buy', 'sell', 'fee', 'profit', 'roi', 'max_buy')
        heads = ('', '품번', '사이즈', '상품명', '매입가', '포이즌', '수수료', '순이익', '수익률', '최대매입가')
        widths = (30, 110, 60, 260, 80, 80, 70, 80, 60, 90)
        self.result = ttk.Treeview(f, columns=cols, show='headings')
        for c, h, w in zip(cols, heads, widths):
            self.result.heading(c, text=h)
            self.result.column(c, width=w, anchor='w' if c == 'name' else 'center')
        self.result.tag_configure('ok', background='#dff5e1')
        self.result.pack(fill='both', expand=True, pady=8)
        self.result.bind('<Double-1>', self.open_url)
        ttk.Label(f, text='행을 더블클릭하면 구매 페이지가 열립니다. 초록색 = 알림 기준 통과').pack(anchor='w')
        self.urls = {}

    def start_scan(self):
        try:
            rows = r.read_watchlist(WATCHLIST)
        except Exception as e:
            messagebox.showerror('오류', f'관심 상품 목록을 읽을 수 없습니다.\n{e}')
            return
        if not rows:
            messagebox.showinfo('안내', '관심 상품 탭에 상품을 먼저 추가하세요.')
            return
        self.scan_btn.state(['disabled'])
        self.status.config(text=f'{len(rows)}개 상품 조회 중...')
        self.done = queue.Queue()
        hook = self.webhook() if self.notify_var.get() else None
        threading.Thread(target=self.run_scan, args=(rows, hook), daemon=True).start()
        self.after(200, self.poll_scan)

    def poll_scan(self):
        # tkinter는 메인 스레드에서만 건드려야 하므로 작업 스레드 결과를 큐로 받는다
        try:
            kind, payload = self.done.get_nowait()
        except queue.Empty:
            self.after(200, self.poll_scan)
            return
        self.scan_btn.state(['!disabled'])
        if kind == 'error':
            self.status.config(text='스캔 실패')
            messagebox.showerror('오류', payload)
        else:
            self.show_results(*payload)

    def run_scan(self, rows, hook):
        cfg = r.load_config(CONFIG)
        try:
            results, errors = r.scan(rows, cfg)
            sent = r.notify_discord(results, hook) if hook else 0
            self.done.put(('ok', (results, errors, sent)))
        except Exception as e:
            self.done.put(('error', str(e)))

    def show_results(self, results, errors, sent):
        self.result.delete(*self.result.get_children())
        self.urls.clear()
        for x in results:
            iid = self.result.insert('', 'end', tags=('ok',) if x['ok'] else (), values=(
                '✅' if x['ok'] else '', x['style_code'], x['size'], x['name'], won(x['buy']), won(x['sell']),
                won(x['fee']), won(x['profit']), f"{x['roi']:.1%}", won(x['max_buy'])))
            self.urls[iid] = x['url']
        hits = sum(x['ok'] for x in results)
        msg = f'완료: {len(results)}개 조회, 기준 통과 {hits}개'
        if sent:
            msg += f', 디스코드 {sent}건 전송'
        if errors:
            msg += f', 오류 {len(errors)}건'
        self.status.config(text=msg)
        if errors:
            messagebox.showwarning('일부 조회 실패', '\n'.join(errors[:15]))

    def open_url(self, _):
        sel = self.result.focus()
        if sel in self.urls:
            webbrowser.open(self.urls[sel])

    # ---- 관심 상품 ----
    def build_watchlist(self, nb):
        f = ttk.Frame(nb, padding=8)
        nb.add(f, text='  관심 상품  ')
        form = ttk.Frame(f)
        form.pack(fill='x')
        self.entries = {}
        for i, (k, label) in enumerate(zip(FIELDS, ('품번', '상품명(선택)', '사이즈(선택)', '포이즌 판매가(원)'))):
            ttk.Label(form, text=label).grid(row=0, column=i, sticky='w', padx=4)
            e = ttk.Entry(form, width=22)
            e.grid(row=1, column=i, padx=4)
            self.entries[k] = e
        ttk.Button(form, text='추가/수정', command=self.add_row).grid(row=1, column=4, padx=4)
        ttk.Button(form, text='선택 삭제', command=self.del_row).grid(row=1, column=5, padx=4)
        self.wl = ttk.Treeview(f, columns=FIELDS, show='headings')
        for k, h in zip(FIELDS, ('품번', '상품명', '사이즈', '포이즌 판매가')):
            self.wl.heading(k, text=h)
        self.wl.pack(fill='both', expand=True, pady=8)
        self.wl.bind('<<TreeviewSelect>>', self.fill_form)
        ttk.Label(f, text='포이즌 판매가는 앱이나 쓰시는 도구에서 확인한 실제 판매 가능가를 넣으세요. 변경은 바로 저장됩니다.').pack(anchor='w')
        self.load_watchlist()

    def load_watchlist(self):
        self.wl.delete(*self.wl.get_children())
        if WATCHLIST.exists():
            for row in r.read_watchlist(WATCHLIST):
                self.wl.insert('', 'end', values=[row.get(k, '') for k in FIELDS])

    def save_watchlist(self):
        import csv
        with open(WATCHLIST, 'w', encoding='utf-8-sig', newline='') as fh:
            w = csv.writer(fh)
            w.writerow(FIELDS)
            for iid in self.wl.get_children():
                w.writerow(self.wl.item(iid, 'values'))

    def fill_form(self, _):
        sel = self.wl.focus()
        if not sel:
            return
        for k, v in zip(FIELDS, self.wl.item(sel, 'values')):
            self.entries[k].delete(0, 'end')
            self.entries[k].insert(0, v)

    def add_row(self):
        vals = [self.entries[k].get().strip() for k in FIELDS]
        try:
            vals[3] = str(int(vals[3].replace(',', '')))
        except ValueError:
            messagebox.showerror('입력 오류', '포이즌 판매가는 숫자로 입력하세요.')
            return
        if not vals[0]:
            messagebox.showerror('입력 오류', '품번을 입력하세요.')
            return
        for iid in self.wl.get_children():
            v = self.wl.item(iid, 'values')
            if v[0] == vals[0] and v[2] == vals[2]:
                self.wl.item(iid, values=vals)
                break
        else:
            self.wl.insert('', 'end', values=vals)
        self.save_watchlist()

    def del_row(self):
        for iid in self.wl.selection():
            self.wl.delete(iid)
        self.save_watchlist()

    # ---- 계산기 ----
    def build_calc(self, nb):
        f = ttk.Frame(nb, padding=16)
        nb.add(f, text='  마진 계산기  ')
        ttk.Label(f, text='매입가(원)').grid(row=0, column=0, sticky='w')
        ttk.Label(f, text='포이즌 판매가(원)').grid(row=1, column=0, sticky='w')
        self.c_buy, self.c_sell = ttk.Entry(f), ttk.Entry(f)
        self.c_buy.grid(row=0, column=1, pady=4)
        self.c_sell.grid(row=1, column=1, pady=4)
        ttk.Button(f, text='계산', command=self.calc).grid(row=2, column=1, sticky='w', pady=8)
        self.c_out = ttk.Label(f, text='', font=('Malgun Gothic', 12))
        self.c_out.grid(row=3, column=0, columnspan=3, sticky='w')

    def calc(self):
        try:
            buy = int(self.c_buy.get().replace(',', ''))
            sell = int(self.c_sell.get().replace(',', ''))
        except ValueError:
            messagebox.showerror('입력 오류', '숫자로 입력하세요.')
            return
        cfg = r.load_config(CONFIG)
        p = r.profit(buy, sell, cfg)
        self.c_out.config(text=f'수수료 {won(r.poizon_fee(sell, cfg))}원\n순이익 {won(p)}원 ({p / buy:.1%})\n'
                               f"최대 매입가 (목표 {won(cfg['min_profit'])}원) {won(r.max_buy_price(sell, cfg))}원")

    # ---- 설정 ----
    def build_settings(self, nb):
        f = ttk.Frame(nb, padding=16)
        nb.add(f, text='  설정  ')
        cfg = r.load_config(CONFIG)
        self.cfg_entries = {}
        for i, (k, label) in enumerate(CFG_LABELS.items()):
            ttk.Label(f, text=label).grid(row=i, column=0, sticky='w', pady=3)
            e = ttk.Entry(f, width=20)
            e.insert(0, str(cfg[k]))
            e.grid(row=i, column=1, sticky='w')
            self.cfg_entries[k] = e
        n = len(CFG_LABELS)
        self.vat_var = tk.BooleanVar(value=cfg['vat_refund'])
        ttk.Checkbutton(f, text='부가세 환급 반영 (일반과세자)', variable=self.vat_var).grid(row=n, column=0, sticky='w', pady=6)
        ttk.Label(f, text='디스코드 웹훅 URL').grid(row=n + 1, column=0, sticky='w')
        self.hook = ttk.Entry(f, width=70)
        self.hook.insert(0, self.webhook() or '')
        self.hook.grid(row=n + 1, column=1, sticky='w')
        ttk.Button(f, text='저장', command=self.save_settings).grid(row=n + 2, column=1, sticky='w', pady=10)
        ttk.Label(f, text='수수료율과 최소 수수료는 포이즌 판매자센터 기준으로 맞추세요.').grid(row=n + 3, column=0, columnspan=2, sticky='w')

    def webhook(self):
        if WEBHOOK_FILE.exists():
            return WEBHOOK_FILE.read_text(encoding='utf-8').strip() or None
        return os.environ.get('DISCORD_WEBHOOK_URL')

    def save_settings(self):
        try:
            cfg = {k: (float if k in ('fee_rate', 'min_roi') else int)(e.get().replace(',', ''))
                   for k, e in self.cfg_entries.items()}
        except ValueError:
            messagebox.showerror('입력 오류', '숫자로 입력하세요.')
            return
        cfg['vat_refund'] = self.vat_var.get()
        CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')
        WEBHOOK_FILE.write_text(self.hook.get().strip(), encoding='utf-8')
        messagebox.showinfo('저장', '설정을 저장했습니다.')


if __name__ == '__main__':
    App().mainloop()
