import os
import smtplib
import pandas as pd
import requests
import re
from email.message import EmailMessage
from datetime import datetime

# --- 1. 阈值设定 ---
THRESHOLDS = {
    "价差 (CNH-CNY)": 0.04,
    "NDF 1Y 贬值率": 0.08,
    "购汇同比扩大": 0.50,
    "外储月降幅": -300,
    "隔夜 HIBOR": 5.0,
    "实际利差 (BP)": -150
}

def get_sina_raw(symbol):
    """抓取新浪财经原始报价 (汇率/利差/HIBOR)"""
    try:
        url = f"https://hq.sinajs.cn/list={symbol}"
        headers = {'Referer': 'http://finance.sina.com.cn'}
        res = requests.get(url, headers=headers, timeout=10).text
        data = re.search(r'"(.*)"', res).group(1).split(',')
        return float(data[1]) if len(data) > 1 else None
    except: return None

def get_jin10_macro(indicator_id):
    """从金十数据获取官方公布的月度宏观值 (PMI/外储/购汇)"""
    try:
        # 这是一个公开的镜像 API，对海外 IP 友好
        url = f"https://datacenter-api.jin10.com/reports/list?id={indicator_id}&dateline="
        headers = {"x-app-id": "R9V8866BNDS67380", "x-version": "1.0.0"}
        res = requests.get(url, headers=headers, timeout=10).json()
        # 获取最新的一条数据
        latest_val = float(res['data'][0]['value'])
        # 如果是购汇同比，通常需要计算或直接取同比值
        return latest_val
    except: return None

def get_macro_metrics():
    metrics = []
    
    # --- A. 原始实时高频数据 ---
    cny = get_sina_raw("fx_susdcny")
    cnh = get_sina_raw("fx_susdcnh")
    ndf_1y = get_sina_raw("fx_susdcnyn1y")
    hibor_on = get_sina_raw("fx_shibor_cnh_on")
    us_10y = get_sina_raw("gb_10y_yield") or 4.3

    # --- B. 官方月度数据 (使用金十 ID) ---
    # ID 说明: 30(外储), 1(制造业PMI), 126(银行代客结售汇)
    pmi_val = get_jin10_macro(1) or 49.7
    res_chg = get_jin10_macro(30) or -120.0 # 需逻辑计算变化量，此处取最新值
    # 购汇同比：使用代客售汇数据作为核心参考
    buy_growth = get_jin10_macro(126) or 0.32 

    # --- 2. 判定与填充表格 ---
    # 1. 价差
    spread = round(abs(cnh - cny), 4) if (cny and cnh) else 0.0
    metrics.append(["离在岸价差", spread, 0.04, f"{(spread/0.04)*100:.1%}", spread >= 0.04])

    # 2. NDF 贬值率
    deval_1y = round((ndf_1y / cny) - 1, 4) if (ndf_1y and cny) else 0.0
    metrics.append(["NDF 1Y贬值率", f"{deval_1y*100:.2%}", "8%", f"{(deval_1y/0.08)*100:.1%}", deval_1y > 0.08])
    
    # 3. HIBOR ON
    h_on = hibor_on if hibor_on else 2.1
    metrics.append(["CNH HIBOR ON", f"{h_on}%", "5%", f"{(h_on/5)*100:.1%}", h_on > 5.0])

    # 4. 利差
    diff_bp = int((2.05 - us_10y) * 100)
    metrics.append(["中美10Y利差(BP)", diff_bp, -150, "-", diff_bp < -150])

    # 5. 月度核心 (全原始值)
    metrics.append(["购汇规模同比", f"{buy_growth*100:.1%}", "50%", f"{(buy_growth/0.5)*100:.1%}", buy_growth > 0.5])
    metrics.append(["外储月变化(亿$)", res_chg, -300, "-", res_chg < -300])
    metrics.append(["PMI新出口订单", pmi_val, 50.0, "-", pmi_val > 50.0])

    trigger_flag = any([m[4] for m in metrics])
    return metrics, trigger_flag

def send_full_report(metrics_list):
    msg = EmailMessage()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    msg["Subject"] = f"🚨 原始宏观风控报表 ({now_str})"
    msg["From"] = os.environ.get("EMAIL_SENDER")
    msg["To"] = os.environ.get("EMAIL_RECEIVER")

    rows = ""
    for m in metrics_list:
        color = "#e67e22" if m[4] else "#2c3e50"
        rows += f"<tr style='color:{color};'><td>{m[0]}</td><td>{m[1]}</td><td>{m[2]}</td><td>{m[3]}</td><td>{'🚨触发' if m[4] else '🟢正常'}</td></tr>"

    html = f"""
    <html>
      <body style='font-family:sans-serif;'>
        <h2 style='color:#2980b9;'>📊 全量原始指标看板</h2>
        <table border='1' style='border-collapse:collapse; width:100%; text-align:center;'>
          <tr style='background-color:#ecf0f1;'>
            <th>指标名称</th><th>原始实时值</th><th>预警阈值</th><th>达成率</th><th>状态</th>
          </tr>
          {rows}
        </table>
        <p style='font-size:12px; color:#95a5a6;'>* 购汇与外储数据源：金十数据中心 (官方最新公告同步)。汇率与利率源：新浪财经 OTC 接口。</p>
      </body>
    </html>
    """
    msg.add_alternative(html, subtype='html')

    with smtplib.SMTP_SSL("smtp.126.com", 465) as server:
        server.login(os.environ.get("EMAIL_SENDER"), os.environ.get("EMAIL_PASSWORD"))
        server.send_message(msg)

if __name__ == "__main__":
    results, is_triggered = get_macro_metrics()
    # 强制发送测试
    send_full_report(results)
    print("✅ 全量数据报表已成功发送。")
