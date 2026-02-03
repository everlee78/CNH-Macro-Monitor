import os
import smtplib
import json
import pandas as pd
import akshare as ak
import yfinance as yf
from email.message import EmailMessage
from datetime import datetime, timedelta

# --- 1. 阈值设定 ---
THRESHOLDS = {
    "价差 (CNH-CNY)": 0.04,
    "NDF隐含贬值率": 0.08,
    "购汇同比扩大": 0.50,
    "外储月降幅 (亿美元)": -300,  # 注意是下降
    "新出口订单": 50.0,
    "实际利差 (BP)": -150,
    "隔夜HIBOR": 5.0
}

def get_macro_metrics():
    metrics = []
    trigger_flag = False
    
    try:
        # A. 汇率价差 (CNH-CNY)
        cny_data = yf.Ticker("CNY=X").history(period="1d")['Close'].iloc[-1]
        cnh_data = yf.Ticker("CNH=X").history(period="1d")['Close'].iloc[-1]
        spread = round(abs(cnh_data - cny_data), 4)
        metrics.append(["价差 (CNH-CNY)", spread, THRESHOLDS["价差 (CNH-CNY)"], f"{(spread/THRESHOLDS['价差 (CNH-CNY)'])*100:.1%}", spread >= 0.04])

        # B. NDF 1Y 隐含贬值率 (简化计算: (NDF-Spot)/Spot)
        ndf_1y = yf.Ticker("CNY1Y=X").history(period="1d")['Close'].iloc[-1]
        devaluation = round((ndf_1y - cny_data) / cny_data, 4)
        metrics.append(["NDF隐含贬值率", devaluation, THRESHOLDS["NDF隐含贬值率"], f"{(devaluation/0.08)*100:.1%}", devaluation > 0.08])

        # C. 中美实际利差 (10Y国债 - 核心通胀/预期, 简化为名义利差)
        cn_bond = ak.bond_china_yield(start_date="20260101").iloc[-1]['10年']
        us_bond = yf.Ticker("^TNX").history(period="1d")['Close'].iloc[-1]
        diff_bp = int((cn_bond - us_bond) * 100)
        metrics.append(["实际利差 (BP)", diff_bp, THRESHOLDS["实际利差 (BP)"], "-", diff_bp < -150])

        # D. 隔夜 HIBOR (模拟抓取，建议使用Akshare)
        hibor = 2.5 # 示例值，实际需匹配TMA接口
        metrics.append(["隔夜HIBOR", hibor, THRESHOLDS["隔夜HIBOR"], f"{(hibor/5)*100:.1%}", hibor > 5.0])

        # E. 月度固定指标 (PMI/外储/购汇)
        # 获取最新PMI
        pmi_df = ak.macro_china_pmi_yearly()
        latest_pmi = pmi_df.iloc[-1]['制造业PMI-新出口订单']
        metrics.append(["PMI新出口订单", latest_pmi, 50.0, "-", latest_pmi > 50.0])

        # 外储变化
        reserve_change = -150 # 亿美元，逻辑：获取本月-上月
        metrics.append(["外储月变化", reserve_change, -300, "-", reserve_change < -300])

    except Exception as e:
        print(f"数据抓取失败: {e}")

    # 检查是否有任何一项触发
    trigger_flag = any([m[4] for m in metrics])
    return metrics, trigger_flag

def send_alert_email(metrics_list):
    msg = EmailMessage()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    msg["Subject"] = f"🚨 宏观风险触发预警！({now_str})"
    msg["From"] = os.environ.get("EMAIL_SENDER")
    msg["To"] = os.environ.get("EMAIL_RECEIVER")

    # 转换为 DataFrame
    df = pd.DataFrame(metrics_list, columns=['指标名称', '实时值', '阈值', '比例/百分比', '是否触发'])
    
    # 高亮触发项的样式
    html_table = df.to_html(index=False, classes='table')
    html_content = f"""
    <html>
      <head>
        <style>
          .table {{ border-collapse: collapse; width: 100%; font-family: sans-serif; }}
          th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
          th {{ background-color: #f2f2f2; }}
          .trigger {{ background-color: #ffcccc; color: red; font-weight: bold; }}
        </style>
      </head>
      <body>
        <h2>宏观风控指标扫描报告</h2>
        <p>扫描时间: {now_str}</p>
        <p style="color:red;"><b>注意：系统检测到以下指标已突破预警线，请及时关注。</b></p>
        {html_table}
      </body>
    </html>
    """
    msg.add_alternative(html_content, subtype='html')

    with smtplib.SMTP_SSL("smtp.126.com", 465) as server:
        server.login(os.environ.get("EMAIL_SENDER"), os.environ.get("EMAIL_PASSWORD"))
        server.send_message(msg)

if __name__ == "__main__":
    results, is_triggered = get_macro_metrics()
    if is_triggered:
        print("🚨 阈值触发，正在发送邮件...")
        send_alert_email(results)
    else:
        print("🟢 所有指标正常，不发送邮件。")
