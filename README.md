# GBN-UDP

## 项目说明

- Project Name：Reliable file transfer using Go-Back-N protocol
- 计网课程Project

## 具体文件说明

- host.py：支持多主机同时进行文件传输
  - 使用多线程+队列
  - 主机间文件传输并发，但是每对连接一个线程，没有实现并发
- log_analysis: 存放log处理程序与产生的log文件
- input_file.txt: 待传输文件
- produce.py: 产生传输文件
- config.json: 配置参数
