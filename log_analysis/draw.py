# 绘制性能分析图，在获得每个变量的analysis结果result.txt后，直接运行，一键生成所有分析的图
import matplotlib.pyplot as plt

pathlist = ["data_size/", "window_num/",
            "error_rate/", "lost_rate/", "timeout/"]
xnamelist = ["DataSize", "WindowNum", "ErrorRate", "LostRate", "TimeOut"]
xlist = [[500, 1000, 1500, 2000, 3000],
         [1, 5, 10, 20, 30],
         [0, 20, 50],
         [0, 20, 50],
         [100, 500, 1000, 1500, 3000]]

for i in range(5):
    total_time = []
    communicate_times = []
    TO_times = []
    NoErr_times = []

    with open(pathlist[i]+"result.txt", "r") as f:
        line = f.readline()
        while line:
            if ("total_time" in line):
                total_time.append(int(float(line[len("total_time:"):-2])))
            elif ("communicate_times" in line):
                communicate_times.append(
                    int(line[len("communicate_times:"):-1]))
            elif ("TO_times" in line):
                TO_times.append(int(line[len("TO_times:"):-1]))
            elif ("NoErr" in line):
                NoErr_times.append(int(line[len("NoErr_times:"):-1]))
            line = f.readline()

    plt.plot(xlist[i], total_time, "-o")
    plt.xlabel(xnamelist[i])
    plt.ylabel("TotalTime/s")
    plt.savefig(pathlist[i]+"totaltime.png")
    plt.clf()

    plt.plot(xlist[i], communicate_times, "-o")
    plt.plot(xlist[i], TO_times, "-o")
    plt.plot(xlist[i], NoErr_times, "-o")
    plt.xlabel(xnamelist[i])
    plt.ylabel("Times")
    plt.legend(["CommunicationTimes", "TOTimes", "NoErrTimes"])
    plt.savefig(pathlist[i]+"times.png")
    plt.clf()
