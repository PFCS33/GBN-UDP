# 产生大于3MB的测试文件
with open("input_file.txt", "w") as f:
    for i in range(450000):
        f.write("{}\n".format(i))
