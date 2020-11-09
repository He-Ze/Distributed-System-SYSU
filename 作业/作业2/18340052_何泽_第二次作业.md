<h1 align=center>分布式系统第二次作业</h1>

<h1 align=center>何泽  18340052</h1>

> CRIU是一种在用户空间实现的进程或者容器`checkpoint` 和`restore`的方法，从而实现进程或者容器的迁移。实际上，CRIU不仅可以实现冷迁移即离线迁移，还可以实现热迁移即在线迁移。 请利用CRIU实现进程和容器的热迁移，并利用样例程序如web server等测试迁移过程中的性能损耗、观察发现，并撰写报告。
>
> 1. https://www.jianshu.com/p/2b288415896c?utm_campaign=maleskine&utm_content=note&utm_medium=seo_notes&utm_source=recommendation;
>
> 2. https://github.com/ZhuangweiKang/Docker-CRIU-Live-Migration; 
>
> 3. https://criu.org/Live_migration;

## 一、版本

- Ubuntu（18.04.1）：

  <img src="/Users/heze/Pictures/截屏/截屏2020-10-19 15.44.12.png" alt="截屏2020-10-19 15.44.12" style="zoom:50%;" />
  
- Docker（已开启实验性功能）

<img src="/Users/heze/Pictures/截屏/截屏2020-10-25 22.12.08.png" alt="截屏2020-10-25 22.12.08" style="zoom:50%;" />

- CRIU（3.14）：

    <img src="/Users/heze/Pictures/截屏/截屏2020-10-19 15.42.10.png" alt="截屏2020-10-19 15.42.10" style="zoom:50%;" />

## 二、进程迁移

- 首先写了如下脚本：

    ```sh
    i=0; while true; do echo $i; i=$(expr $i + 1); sleep 1; done
    ```

    每秒钟计数加一

- 查看当前进程PID

    ```sh
    pgrep -f test.sh
    ```

    

    <img src="/Users/heze/Pictures/截屏/截屏2020-10-19 19.45.04.png" alt="截屏2020-10-19 19.45.04" style="zoom:50%;" />

- 使用dump保存进程镜像

    ```bash
    sudo criu dump --t 1150 --images-dir ~/Desktop/test --shell-job
    ```

    <img src="/Users/heze/Pictures/截屏/截屏2020-10-19 19.45.22.png" alt="截屏2020-10-19 19.45.22" style="zoom:50%;" />

- 运行状态

    <img src="/Users/heze/Pictures/截屏/截屏2020-10-19 19.45.32.png" alt="截屏2020-10-19 19.45.32" style="zoom:50%;" />

    可以看到，运行至15时被停止、保存

- 可以看到此时生成了很多img文件：

    <img src="/Users/heze/Pictures/截屏/截屏2020-10-19 19.53.05.png" alt="截屏2020-10-19 19.53.05" style="zoom:50%;" />

- 压缩：

  ```bash
  tar -cvf test.tar.gz ~/Desktop/test
  ```
  
    <img src="/Users/heze/Pictures/截屏/截屏2020-10-19 19.55.58.png" alt="截屏2020-10-19 19.55.58" style="zoom:50%;" />
  
- 我使用U盘将压缩文件拷贝至另一台机器，并解压缩：

    ```bash
    tar -xvf ~/Desktop/test.tar.gz
    ```

    <img src="/Users/heze/Pictures/截屏/截屏2020-10-19 19.59.19.png" alt="截屏2020-10-19 19.59.19" style="zoom:50%;" />

- 恢复：

    ```bash
    sudo criu restore -t 1200 --images-dir ~/Desktop/test --shell-job
    ```

    <img src="/Users/heze/Pictures/截屏/截屏2020-10-19 20.01.31.png" alt="截屏2020-10-19 20.01.31" style="zoom:50%;" />

**可以看到从16开始计数，恢复成功**

## 三、Docker迁移

- 首先运行一个容器，每5秒加一

    ```bash
    docker run -d --name looper2 --security-opt seccomp:unconfined busybox  \
             /bin/sh -c 'i=0; while true; do echo $i; i=$(expr $i + 1); sleep 5; done'
    ```

    <img src="/Users/heze/Pictures/截屏/截屏2020-10-25 22.50.33.png" alt="截屏2020-10-25 22.50.33" style="zoom:50%;" />

- 使用`checkpoint`保存状态，保存到`/home`目录下

    ```bash
    docker checkpoint create --checkpoint-dir=/home looper2 checkpoint2
    ```

    <img src="/Users/heze/Pictures/截屏/截屏2020-10-25 22.50.45.png" alt="截屏2020-10-25 22.50.45" style="zoom:50%;" />

- 此时`/home`目录下会生成ID名的文件夹，进去`/checkpoints/checkpoint2`就可以看到镜像文件

    ![截屏2020-10-25 22.51.04](/Users/heze/Pictures/截屏/截屏2020-10-25 22.51.04.png)

- 和上面一样，压缩，用U盘传到另一台电脑，再解压缩

- 首先只创建但不运行一个容器，命名为`looper3`

    ```bash
    docker create --name looper3 --security-opt seccomp:unconfined busybox \
             /bin/sh -c 'i=0; while true; do echo $i; i=$(expr $i + 1); sleep 1; done'
    ```

    <img src="/Users/heze/Pictures/截屏/截屏2020-10-25 23.10.34.png" alt="截屏2020-10-25 23.10.34" style="zoom:50%;" />

- 恢复：

    ```bash
    docker start --checkpoint-dir=/home --checkpoint=checkpoint2 looper3
    ```

    <img src="/Users/heze/Pictures/截屏/截屏2020-10-25 23.10.57.png" alt="截屏2020-10-25 23.10.57" style="zoom:50%;" />

**可以看到从前面的断点7继续，从8开始，迁移成功**

至此，进程和容器的热迁移全部成功。