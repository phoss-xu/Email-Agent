#!/usr/bin/env python3
"""测试日报图片生成"""
import sys
import os
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path

# 添加项目路径
sys.path.insert(0, '/Users/zhichao.xu-a2085/play/email_agent')

# 先导入 email.message 标准库，避免冲突
import email.message

from report_generator import ReportGenerator


@dataclass
class MockEmail:
    """模拟邮件数据"""
    message_id: str
    subject: str
    sender: str
    sender_domain: str
    date: datetime
    body: str
    is_read: bool = False
    recipients: list = None
    cc: list = None
    category: str = 'external_normal'
    match_reason: str = ''
    summary: str = ''


def make_mock_data():
    """构造模拟数据"""
    now = datetime.now()

    internal_meeting = [
        MockEmail('msg1', 'Q3产品周会纪要（8月17日）', '张三 <zhangsan@aqara.com>',
                  'aqara.com', now, '本次周会主要讨论了Q3产品迭代计划、智能门锁固件升级时间表以及海外渠道上线进度，会议纪要见附件...',
                  True, 'internal_meeting', '内部-会议记录关键词匹配',
                  '本次周会主要讨论了Q3产品迭代计划、智能门锁固件升级时间表以及海外渠道上线进度...'),
        MockEmail('msg2', '月度经营分析会会议纪要', '李四 <lisi@aqara.com>',
                  'aqara.com', now, '月度经营分析会议于8月15日召开，重点复盘了7月销售额与渠道库存情况...',
                  True, 'internal_meeting', '内部-会议记录关键词匹配',
                  '月度经营分析会议于8月15日召开，重点复盘了7月销售额与渠道库存情况...'),
    ]

    internal_hr = [
        MockEmail('msg3', '7月工资条已发放，请查收', 'HR部门 <hr@aqara.com>',
                  'aqara.com', now, '各位同事，7月工资条已发放至HR系统，请登录查看，如有疑问请联系人事部...',
                  True, 'internal_hr', '内部-HR关键词匹配',
                  '各位同事，7月工资条已发放至HR系统，请登录查看，如有疑问请联系人事部...'),
    ]

    internal_reply = [
        MockEmail('msg4', '请确认Q3预算方案', '王五 <wangwu@aqara.com>',
                  'aqara.com', now, '请于本周五前确认Q3市场预算方案，确认后我们将启动供应商采购流程...',
                  True, 'internal_reply', '内部-需回复关键词匹配',
                  '请于本周五前确认Q3市场预算方案，确认后我们将启动供应商采购流程...'),
    ]

    internal_other = [
        MockEmail('msg5', '团建活动报名通知', '行政部 <admin@aqara.com>',
                  'aqara.com', now, '公司将于9月组织年度团建，请各部门统计报名人数...', True, 'internal_other', '内部邮件'),
    ]

    important = [
        MockEmail('msg6', 'Apple ID 安全提醒', 'Apple <no-reply@apple.com>',
                  'apple.com', now, '您的 Apple ID 在陌生设备上登录，请及时确认...', True, 'important', '域名匹配: apple.com',
                  '您的 Apple ID 在陌生设备上登录，请及时确认...'),
        MockEmail('msg7', '合同到期续签确认', '某客户 <contact@client.com>',
                  'client.com', now, '双方合作协议将于下月到期，请确认是否续签...', True, 'important', '关键词匹配',
                  '双方合作协议将于下月到期，请确认是否续签...'),
    ]

    invoice = [
        MockEmail('msg8', '采购订单发票-京东', '京东 <invoice@jd.com>',
                  'jd.com', now, '您的采购订单已完成，发票已开具...', True, 'invoice', '发票关键词'),
    ]

    spam = [
        MockEmail(f'spam{i}', f'广告邮件{i}', f'promo{i}@spam.com',
                  'spam.com', now, '限时优惠...', True, 'spam', '垃圾关键词')
        for i in range(8)
    ]

    external_normal = [
        MockEmail(f'norm{i}', f'外部日常通知{i}', f'user{i}@mail.com',
                  'mail.com', now, '这是一封普通外部邮件...', True, 'external_normal', '')
        for i in range(10)
    ]

    all_emails = internal_meeting + internal_hr + internal_reply + internal_other + important + invoice + spam + external_normal

    return {
        'total': all_emails,
        'internal_meeting': internal_meeting,
        'internal_hr': internal_hr,
        'internal_reply': internal_reply,
        'internal_other': internal_other,
        'important': important,
        'invoice': invoice,
        'spam': spam,
        'external_normal': external_normal,
    }


if __name__ == '__main__':
    data = make_mock_data()
    gen = ReportGenerator()
    path = gen.generate_image(data)
    if path:
        print(f"\n✅ 图片已生成: {path}")
    else:
        print("\n❌ 图片生成失败")
