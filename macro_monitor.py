import os
import smtplib
import pandas as pd
import requests
from email.message import EmailMessage
from datetime import datetime

def get_data():
    """获取金融数据（利用新浪财经等公开接口）"""
    res_data = {}
    try:
        # 获取汇率快照 (USDCNY, USDCNH)
        url = "https://hq.sinajs.cn/list=fx_susd_cny,fx_susdcnh"
        # 备注：实际代码中会处理编码，此处简化逻辑
        res_data['离岸人民币 (CNH)'] = "需通过yfinance获取" 
        res_data['在岸人民币 (CNY)'] = "7.2000" # 演示占位
        
        # 中美利差逻辑
        res_data['10Y中美利差'] = "-150BP"
    except:
        pass
    return res_data

def send_mail(content_dict):
    msg = EmailMessage()
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    msg["Subject"] = f"📊 汇率宏观监控报表 - {now}"
    msg["From"] = os.environ.get("EMAIL_SENDER")
    msg["To"] = os.environ.get("EMAIL_RECEIVER")
    
    # 构造表格 HTML
    df = pd.DataFrame(list(content_dict.items()), columns=['指标', '当前数值'])
    html = f"<h3>宏观数据日报</h3>{df.to_html(index=False)}"
    msg.add_alternative(html, subtype='html')
    
    with smtplib.SMTP_SSL("smtp.126.com", 465) as server:
        server.login(os.environ.get("EMAIL_SENDER"), os.environ.get("EMAIL_PASSWORD"))
        server.send_message(msg)

if __name__ == "__main__":
    data = {"USD/CNY": "7.2450", "USD/CNH": "7.2580", "价差": "130pips", "10Y利差": "-180BP"}
    send_mail(data)
