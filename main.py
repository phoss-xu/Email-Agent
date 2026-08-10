#!/usr/bin/env python3
"""邮件监控系统入口"""
from scheduler import EmailScheduler


def main():
    """主函数"""
    scheduler = EmailScheduler()
    scheduler.start()


if __name__ == '__main__':
    main()
