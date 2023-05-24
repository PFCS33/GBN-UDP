# 读取log文件，输出统计信息
# 输入输出路径（分析的哪个变量）
pathlist = ["data_size/", "window_num/",
            "error_rate/", "lost_rate/", "timeout/"]
numlist=[5,5,3,3,5]
#目标统计信息
total_time=0
communicate_times=0
TOtimes=0
NoErrtimes=0

for k in range(5):
    for i in range(numlist[k]):
        total_time=0
        communicate_times=0
        TOtimes=0
        NoErrtimes=0
        #处理
        with open(pathlist[k]+"log{}.txt".format(i+1),"r") as f:
            line=f.readline()
            while line:
                communicate_times+=1
                if(line[0:4]=="SEND"):
                    if("TO" in line):
                        TOtimes+=1
                elif(line[0:4]=="RECV"):
                    if("NoErr" in line):
                        NoErrtimes+=1
                elif("total_time" in line):
                    index=line.find("total_time")
                    total_time=line[index+len("total_time:"):]
                line=f.readline()
        #注意，这是追加模式，想要重新生成日志文件的分析，需要先删除旧的日志文件
        with open(pathlist[k]+"result.txt","a+") as f:
            f.write("total_time:{}\n".format(total_time))
            f.write("communicate_times:{}\n".format(communicate_times))
            f.write("TO_times:{}\n".format(TOtimes))
            f.write("NoErr_times:{}\n\n".format(NoErrtimes))


