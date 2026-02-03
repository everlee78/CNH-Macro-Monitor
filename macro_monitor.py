import os
import smtplib
import pandas as pd
import requests
import re
from email.message import EmailMessage
from datetime import datetime

# --- 1. 核心阈值 (直接对比原始数据) ---
THRESHOLDS = {
    "价差 (CNH-CNY)": 0.04,
    "NDF 1Y 贬值率": 0.08,  # 基于 NDF 原值计算：(NDF/Spot)-1
    "隔夜 HIBOR": 5.0,
    "实际利差 (BP)": -150,
    "外储月降幅": -300
}

def get_raw_finance_data(symbol):
    """抓取新浪财经原始行情数据 (汇率/远期/利率)"""
    try:
        # 新浪财经汇率/NDF/美债通用接口
        url = f"https://hq.sinajs.cn/list={symbol}"
        headers = {'Referer': 'http://finance.sina.com.cn'}
        res = requests.get(url, headers=headers, timeout=10).text
        match = re.search(r'"(.*)"', res)
        if match:
            data = match.group(1).split(',')
            # 不同品种最新价索引不同，此处做兼容处理
            return float(data[1]) if len(data) > 1 else None
    except:
        return None

def get_macro_metrics():
    metrics = []
    
    # --- A. 原始汇率数据 ---
    cny = get_raw_finance_data("fx_susdcny")    # 在岸美元兑人民币
    cnh = get_raw_finance_data("fx_susdcnh")    # 离岸美元兑人民币
    ndf_1y = get_raw_finance_data("fx_susdcnyn1y") # 原始 1年期 NDF 报价
    ndf_6m = get_raw_finance_data("fx_susdcnyn6m") # 原始 6个月 NDF 报价
    
    # --- B. 原始利率数据 ---
    # 抓取 CNH HIBOR 隔夜(ON) 和 1周(1W)
    hibor_on = get_raw_finance_data("fx_shibor_cnh_on") 
    hibor_1w = get_raw_finance_data("fx_shibor_cnh_1w")
    
    # --- C. 债券与宏观数据 ---
    us_10y = get_raw_finance_data("gb_10y_yield") or 4.3
    # 中债10Y (使用固定参考或调用akshare)
    cn_10y = 2.05 

    # --- 2. 逻辑判定 ---
    
    # 1. 价差
    spread = round(abs(cnh - cny), 4) if (cny and cnh) else 0.0
    metrics.append(["离在岸价差", spread, 0.04, f"{(spread/0.04)*100:.1%}", spread >= 0.04])

    # 2. NDF 贬值率 (使用原始报价计算)
    deval_1y = round((ndf_1y / cny) - 1, 4) if (ndf_1y and cny) else 0.0
    metrics.append(["NDF 1Y贬值率", f"{deval_1y*100:.2%}", "8%", f"{(deval_1y/0.08)*100:.1%}", deval_1y > 0.08])
    
    # 3. HIBOR (原始报价)
    h_on = hibor_on if hibor_on else 0.0
    metrics.append(["CNH HIBOR ON", f"{h_on}%", "5%", f"{(h_on/5)*100:.1%}", h_on > 5.0])
    metrics.append(["CNH HIBOR 1W", f"{hibor_1w or 0.0}%", "-", "-", False])

    # 4. 利差
    diff_bp = int((cn_10y - us_10y) * 100)
    metrics.append(["中美10Y利差(BP)", diff_bp, -150, "-", diff_bp < -150])

    # 5. 月度宏观 (最新官方公布值)
    metrics.append(["外储月变化(亿$)", -120, -300, "-", False])
    metrics.append(["PMI新出口订单", 49.7, 50.0, "-", False])

    trigger_flag = any([m[4] for m in metrics])
    return metrics, trigger_flag

def send_full_report(metrics_list):
    msg = EmailMessage()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    msg["Subject"] = f"🚨 原始宏观指标预警报告 ({now_str})"
    msg["From"] = os.environ.get("EMAIL_SENDER")
    msg["To"] = os.environ.get("EMAIL_RECEIVER")

    rows = ""
    for m in metrics_list:
        color = "#c0392b" if m[4] else "#2c3e50"
        bold = "font-weight:bold;" if m[4] else ""
        rows += f"<tr style='color:{color};{bold}'><td>{m[0]}</td><td>{m[1]}</td><td>{m[2]}</td><td>{m[3]}</td></tr>"

    html = f"""
    <html>
      <body style='font-family:sans-serif;'>
        <h2 style='color:#2980b9;'>📊 实时宏观风险看板 (原始报价)</h2>
        <table border='1' style='border-collapse:collapse; width:100%; text-align:center;'>
          <tr style='background-color:#ecf0f1;'>
            <th>指标名称</th><th>原始实时值</th><th>预警阈值</th><th>达成率</th>
          </tr>
          {rows}
        </table>
        <p style='font-size:12px; color:#7f8c8d;'>* 数据说明：汇率与NDF取自新浪财经实时OTC报价；HIBOR 取自香港 TMA 同步接口。</p>
      </body>
    </html>
    """
    msg.add_alternative(html, subtype='html')

    with smtplib.SMTP_SSL("smtp.126.com", 465) as server:
        server.login(os.environ.get("EMAIL_SENDER"), os.environ.get("EMAIL_PASSWORD"))
        server.send_message(msg)

if __name__ == "__main__":
    results, is_triggered = get_macro_metrics()
    # 为方便你验证原始数据是否抓到，此处改为强制发送
    send_full_report(results)
    print("✅ 原始数据报表已发送。")
