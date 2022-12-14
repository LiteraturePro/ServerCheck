import os, signal
from random import randrange
from flask import Flask, render_template, jsonify, request, escape
from pyecharts import options as opts
from pyecharts.charts import Bar, Line, Liquid, Gauge, Grid
import pyecharts.options as opts
import time
import psutil

import requests
import json
import threading
from socket import gaierror, gethostbyname
from multiprocessing.dummy import Pool as ThreadPool
from urllib.parse import urlparse
from time import gmtime, strftime
from settings import refresh_interval, filename, site_down, number_threads, include_search



from flask_bootstrap import Bootstrap

import sentry_sdk
from flask import Flask
from sentry_sdk.integrations.flask import FlaskIntegration

sentry_sdk.init(
    dsn="https://103ac223f0e6447c9ddedd63cc08bdfb@o513531.ingest.sentry.io/4503940523294720",
    integrations=[
        FlaskIntegration(),
    ],

    # Set traces_sample_rate to 1.0 to capture 100%
    # of transactions for performance monitoring.
    # We recommend adjusting this value in production.
    traces_sample_rate=1.0
)




app = Flask(__name__, static_folder="templates")

Bootstrap(app)

## 第一部分
def is_reachable(url):
    """ This function checks to see if a host name has a DNS entry
    by checking for socket info."""
    try:
        gethostbyname(url)
    except gaierror:
        return False
    else:
        return True


def get_status_code(url):
	""" This function returns the status code of the url."""
	try:
	    status_code = requests.get(url, timeout=30).status_code
	    return status_code
	except requests.ConnectionError:
	    return site_down


def check_single_url(url):
    """This function checks a single url and if connectable returns
    the status code, else returns variable site_down (default: UNREACHABLE)."""
    if is_reachable(urlparse(url).hostname) == True:
        return str(get_status_code(url))
    else:
        return site_down


def launch_checker():
    """This function launches the check_multiple_urls function every x seconds
    (defined in refresh interval variable)."""
    t = threading.Timer(refresh_interval, launch_checker)
    t.daemon=True
    t.start()
    global returned_statuses
    returned_statuses = check_multiple_urls()


def check_multiple_urls():
    """This function checks through urls specified in the checkurls.json file
    (specified in the filename variable) and
    returns their statuses as a dictionary."""
    statuses = {}
    temp_list_statuses = []
    global last_update_time
    pool = ThreadPool(number_threads)
    temp_list_statuses = pool.map(check_single_url, list_urls)
    for i in range(len(list_urls)):
        statuses[list_urls[i]] = temp_list_statuses[i]
    last_update_time = strftime("%Y-%m-%d %H:%M:%S", gmtime())
    return statuses

def compare_submitted(submitted):
    """This function checks whether the value in the dictionary is found in 
    the checkurls.json file. """
    stripped_submission = https_start_strip(submitted)
    if stripped_submission in list_urls:
        flaggy = True
    else:
        flaggy = False
    return (flaggy, stripped_submission)

def https_start_strip(url):
    url = url.strip().lower()
    if url[:7] == 'http://':
        return url
    elif url[:8] == 'https://':
        return url
    else:
        url = "https://" + url
        return url

def generate_list_urls(input_dict):
    list_urls = []
    for group, urls in input_dict.items():
        for url in urls:
            list_urls.append(url)
    return list_urls


@app.route("/url", methods=["GET"])
def display_returned_statuses():
    return render_template(
        'indexurl.html',
        returned_statuses = returned_statuses,
        checkurls = checkurls,
        last_update_time = last_update_time,
        include_search = include_search
        )
        

@app.route('/result',methods = ['POST'])
def result():
    if request.method == 'POST':
        results = compare_submitted(escape(request.form['submitted']))
        return render_template(
        'indexurl.html',
        results = results,
        returned_statuses = returned_statuses,
        checkurls = checkurls,
        last_update_time = last_update_time
        )


@app.route("/api", methods=["GET"])
def display_returned_api():
    return jsonify(
        returned_statuses
        ),200


with open(filename) as f:
    checkurls = json.load(f)
list_urls = generate_list_urls(checkurls)
returned_statuses = {}
last_update_time = 'time string'


## 第二部分


cpu_percent_dict = {}
net_io_dict = {'net_io_time':[], 'net_io_sent': [], 'net_io_recv': [], 'pre_sent': 0, 'pre_recv': 0, 'len': -1}
disk_dict = {'disk_time':[], 'write_bytes': [], 'read_bytes': [], 'pre_write_bytes': 0, 'pre_read_bytes': 0, 'len': -1}

def cpu():
    now = time.strftime('%H:%M:%S', time.localtime(time.time()))
    cpu_percent = psutil.cpu_percent()
    cpu_percent_dict[now] = cpu_percent
    # 保持在图表中 10 个数据
    if len(cpu_percent_dict.keys()) == 11:
        cpu_percent_dict.pop(list(cpu_percent_dict.keys())[0])


def cpu_line() -> Line:
    now = time.strftime('%Y年%m月%d日的', time.localtime(time.time()))
    cpu()
    c = (
        Line()
            .add_xaxis(list(cpu_percent_dict.keys()))
            .add_yaxis('', list(cpu_percent_dict.values()), areastyle_opts=opts.AreaStyleOpts(opacity=0.5))
            .set_global_opts(title_opts=opts.TitleOpts(title = now + "CPU负载",pos_left = "center"),
                             yaxis_opts=opts.AxisOpts(min_=0,max_=100,split_number=10,type_="value", name='%'))
    )
    return c

def memory():
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return memory.total, memory.total - (memory.free + memory.inactive), memory.free + memory.inactive, swap.total, swap.used, swap.free, memory.percent


def memory_liquid() -> Gauge:
    mtotal, mused, mfree, stotal, sused, sfree, mpercent = memory()
    c = (
        Gauge()
            .add("", [("", mpercent)])
            .set_global_opts(title_opts=opts.TitleOpts(title="内存负载", pos_left = "center"))
    )
    return mtotal, mused, mfree, stotal, sused, sfree, c



def net_io():
    now = time.strftime('%H:%M:%S', time.localtime(time.time()))
    # 获取网络信息
    count = psutil.net_io_counters()
    g_sent = count.bytes_sent
    g_recv = count.bytes_recv

    # 第一次请求
    if net_io_dict['len'] == -1:
        net_io_dict['pre_sent'] = g_sent
        net_io_dict['pre_recv'] = g_recv
        net_io_dict['len'] = 0
        return

    # 当前网络发送/接收的字节速率 = 现在网络发送/接收的总字节 - 前一次请求网络发送/接收的总字节
    net_io_dict['net_io_sent'].append(g_sent - net_io_dict['pre_sent'])
    net_io_dict['net_io_recv'].append(g_recv - net_io_dict['pre_recv'])
    net_io_dict['net_io_time'].append(now)
    net_io_dict['len'] = net_io_dict['len'] + 1

    net_io_dict['pre_sent'] = g_sent
    net_io_dict['pre_recv'] = g_recv

    # 保持在图表中 10 个数据
    if net_io_dict['len'] == 11:
        net_io_dict['net_io_sent'].pop(0)
        net_io_dict['net_io_recv'].pop(0)
        net_io_dict['net_io_time'].pop(0)
        net_io_dict['len'] = net_io_dict['len'] - 1


def net_io_line() -> Line:
    net_io()

    c = (
    Line()
    .add_xaxis(net_io_dict['net_io_time'])
    .add_yaxis("发送字节数", net_io_dict['net_io_sent'], is_smooth=True)
    .add_yaxis("接收字节数", net_io_dict['net_io_recv'], is_smooth=True)
    .set_series_opts(
        areastyle_opts=opts.AreaStyleOpts(opacity=0.5),
        label_opts=opts.LabelOpts(is_show=False),
    )
    .set_global_opts(
        title_opts=opts.TitleOpts(title="网卡IO", pos_left = "center"),
        xaxis_opts=opts.AxisOpts(
            axistick_opts=opts.AxisTickOpts(is_align_with_label=True),
            is_scale=False,
            boundary_gap=False,
        ),
        yaxis_opts=opts.AxisOpts(type_="value", name='B/2S'),
        legend_opts=opts.LegendOpts(pos_left="left"),
    ))
    return c


def process():
    result = []
    process_list = []
    pid = psutil.pids()
    for k, i in enumerate(pid):
        try:
            proc = psutil.Process(i)
            ctime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(proc.create_time()))
            process_list.append((str(i), proc.name(), proc.cpu_percent(), proc.memory_percent(), ctime))
        except psutil.AccessDenied:
            pass
        except psutil.NoSuchProcess:
            pass
        except SystemError:
            pass

        process_list.sort(key=process_sort, reverse=True)
    for i in process_list:
        result.append({'PID': i[0], 'name': i[1], 'cpu': i[2], 'mem': "%.2f%%"%i[3], 'ctime': i[4]})


    return jsonify({'list': result})

def process_sort(elem):
    return elem[3]


def disk():
    disk_usage = psutil.disk_usage('/')
    disk_used = 0
    # 磁盘已使用大小 = 每个分区的总和
    partitions = psutil.disk_partitions()
    for partition in partitions:
        partition_disk_usage = psutil.disk_usage(partition[1])
        disk_used = partition_disk_usage.used + disk_used

    now = time.strftime('%H:%M:%S', time.localtime(time.time()))
    count = psutil.disk_io_counters()
    read_bytes = count.read_bytes
    write_bytes = count.write_bytes

    # 第一次请求
    if disk_dict['len'] == -1:
        disk_dict['pre_write_bytes'] = write_bytes
        disk_dict['pre_read_bytes'] = read_bytes
        disk_dict['len'] = 0
        return disk_usage.total, disk_used, disk_usage.free

    # 当前速率=现在写入/读取的总字节-前一次请求写入/读取的总字节
    disk_dict['write_bytes'].append((write_bytes - disk_dict['pre_write_bytes'])/1024)
    disk_dict['read_bytes'].append((read_bytes - disk_dict['pre_read_bytes'])/ 1024)
    disk_dict['disk_time'].append(now)
    disk_dict['len'] = disk_dict['len'] + 1

    # 把现在写入/读取的总字节放入前一个请求的变量中
    disk_dict['pre_write_bytes'] = write_bytes
    disk_dict['pre_read_bytes'] = read_bytes

    # 保持在图表中 50 个数据
    if disk_dict['len'] == 51:
        disk_dict['write_bytes'].pop(0)
        disk_dict['read_bytes'].pop(0)
        disk_dict['disk_time'].pop(0)
        disk_dict['len'] = disk_dict['len'] - 1

    return disk_usage.total, disk_used, disk_usage.free


def disk_line() -> Line:
    total, used, free = disk()

    c = (
        Line(init_opts=opts.InitOpts(width="1680px", height="800px"))
        .add_xaxis(xaxis_data=disk_dict['disk_time'])
        .add_yaxis(
            series_name="写入数据",
            y_axis=disk_dict['write_bytes'],
            areastyle_opts=opts.AreaStyleOpts(opacity=0.5),
            linestyle_opts=opts.LineStyleOpts(),
            label_opts=opts.LabelOpts(is_show=False),
        )
        .add_yaxis(
            series_name="读取数据",
            y_axis=disk_dict['read_bytes'],
            yaxis_index=1,
            areastyle_opts=opts.AreaStyleOpts(opacity=0.5),
            linestyle_opts=opts.LineStyleOpts(),
            label_opts=opts.LabelOpts(is_show=False),
        )
        .extend_axis(
            yaxis=opts.AxisOpts(
                name_location="start",
                type_="value",
                is_inverse=True,
                axistick_opts=opts.AxisTickOpts(is_show=True),
                splitline_opts=opts.SplitLineOpts(is_show=True),
                name='KB/2S'
            )
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(
                title="磁盘IO",
                pos_left="center",
                pos_top="top",
            ),
            tooltip_opts=opts.TooltipOpts(trigger="axis", axis_pointer_type="cross"),
            legend_opts=opts.LegendOpts(pos_left="left"),
            xaxis_opts=opts.AxisOpts(type_="category", boundary_gap=False),
            yaxis_opts=opts.AxisOpts(type_="value", name='KB/2S'),
        )
        .set_series_opts(
            axisline_opts=opts.AxisLineOpts(),
        )
    )

    return total, used, free, c

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/cpu")
def get_cpu_chart():
    c = cpu_line()
    return c.dump_options_with_quotes()

@app.route("/memory")
def get_memory_chart():
    mtotal, mused, mfree, stotal, sused, sfree, c = memory_liquid()
    return jsonify({'mtotal': mtotal, 'mused': mused, 'mfree': mfree, 'stotal': stotal, 'sused': sused, 'sfree': sfree, 'liquid': c.dump_options_with_quotes()})


@app.route("/netio")
def get_net_io_chart():
    c = net_io_line()
    return c.dump_options_with_quotes()

@app.route("/process")
def get_process_tab():
    c = process()
    return c

@app.route("/delprocess")
def del_process():
    pid = request.args.get("pid")
    os.kill(int(pid), signal.SIGKILL)
    return jsonify({'status': 'OK'})

@app.route("/disk")
def get_disk_chart():
    total, used, free, c = disk_line()
    return jsonify({'total': total, 'used': used, 'free': free, 'line': c.dump_options_with_quotes()})

## 第三部分

@app.route("/nezha")
def get_nezha_api():
    url = "http://194.87.236.155:8008/api/v1/server/details?id=6,17,18,22,23"
    headers = {
	    "Authorization": "fd88a2eb05fb6ecf049cca8811e6473d"
    }
    res = requests.get(url,headers=headers)
    return jsonify(json.loads(res.text))


@app.route('/debug-sentry')
def trigger_error():
    division_by_zero = 1 / 0


if __name__ == "__main__":
    launch_checker()
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
