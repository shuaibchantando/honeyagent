#!/usr/bin/env python3
import os, time, datetime, string, base64, sys
import subprocess, multiprocessing
import json, requests
import configparser
import logging, logging.handlers
import psutil

class HoneyAgent(multiprocessing.Process):
    """ Main process for HoneyAgent """

    def __init__(self):
        multiprocessing.Process.__init__(self)
        self.maindir = os.path.dirname(os.path.abspath(__file__))
        self.config_path = os.path.join(self.maindir, 'conf.ini')
        self.config = configparser.ConfigParser()
        self.config.read(self.config_path)
        self.initLogging()
        if not os.path.isfile(self.config_path):
            self.logger.error("Config file not found")
            exit()

    def initLogging(self):  
        logging.captureWarnings(True)
        self.logger = logging.getLogger('honeyagent')
        self.logger.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        # log console handler 
        consoleHandler = logging.StreamHandler()
        consoleHandler.setFormatter(formatter)
        self.logger.addHandler(consoleHandler)
        self.logger.info("HoneyAgent v2.0")

    def cmd(self, command):
        return subprocess.Popen(command, shell=True, stdout=subprocess.PIPE).communicate()[0]

    def getHoneypotStatus(self):
        kippo = self.cmd("ps aux | grep [c]owrie")
        dionaea = self.cmd("ps aux | grep [d]ionaea")
        glastopf = self.cmd("ps aux | grep [g]lastopf")
        return {
            'kippo': 'down' if not kippo else 'up',
            'dionaea': 'down' if not dionaea else 'up',
            'glastopf': 'down' if not glastopf else 'up'
        }

    def getUptime(self):
        up = float(os.popen('cat /proc/uptime').read().split(" ")[0])
        parts = []
        days, up = up // 86400, up % 86400
        if days:
            parts.append('%d day%s' % (days, 's' if days != 1 else ''))

        hours, up = up // 3600, up % 3600
        if hours:
            parts.append('%d hour%s' % (hours, 's' if hours != 1 else ''))

        minutes, up = up // 60, up % 60
        if minutes:
            parts.append('%d minute%s' % (minutes, 's' if minutes !=1 else ''))

        if up or not parts:
            parts.append('%.2f seconds' % up)

        return '%s' % ', '.join(parts)

    def getNetworkUsage(self):
        netjsons = []

        for x in os.popen('ip link ls up | grep BROADCAST | cut -d: -f2').read().split():
            if len(x) < 8:
                if not x in ["sit0","lo"]:
                    try:
                        netjson = {
                            'interface': x,
                            'ip': os.popen('ip addr show %s' % x).read().split("inet ")[1].split("/")[0]
                        }
                        netjsons.append(netjson)
                    except Exception as e:
                        netjson = {
                            'interface': x,
                            'ip': 'Not Assigned'
                        }
                        netjsons.append(netjson)

        return netjsons

    def getHDDInfo(self):
        hddjsons = []

        block, total, used, free, percent, mount = os.popen('df %s | tail -1' % self.config.get('config', 'mount')).read().split()

        hddjson = {
            'mount': mount,
            'free': int(free) * 1024,
            'percent': percent[:-1],
            'total': int(total) * 1024,
            'used': int(used) * 1024
        }
        hddjsons.append(hddjson)
        return hddjsons

    def getAllInfo(self):
        info = {
            'uptime': self.getUptime(),
            'last_boot': datetime.datetime.fromtimestamp(psutil.boot_time()),
            'server_datetime': datetime.datetime.now(),
            'netusage': self.getNetworkUsage(),
            'hdd': self.getHDDInfo(),
            'ram': {
                'used': psutil.virtual_memory().used,
                'percent': psutil.virtual_memory().percent,
                'total': psutil.virtual_memory().total,
                'free': psutil.virtual_memory().free
            },
            'swap': {
                'used': psutil.swap_memory().used,
                'percent': psutil.swap_memory().percent,
                'total': psutil.swap_memory().total,
                'free': psutil.swap_memory().free
            },
            'services': self.getHoneypotStatus()
        }

        def date_handler(obj):
            return obj.isoformat() if hasattr(obj, 'isoformat') else obj

        return json.dumps(info, default=date_handler)

    def SuperEncrypt(self, text):
        STD_ALPHABET = b'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/='
        CUST_ALPHABET = b'Aa0Bb1Cc2Dd3Ee4Ff5Gg6Hh7Ii8Jj9KkLlMmNnOoPpQqRrSsTtUuVvWwXxYyZz+/='
        ENC_TRANS = bytes.maketrans(STD_ALPHABET, CUST_ALPHABET)
        return base64.b64encode(str.encode(text)).translate(ENC_TRANS)

    def SendHeartbeat(self):
        self.logger.info("Sending heartbeat")
        url = '%s%s/heartbeat' % (self.config.get('config', 'cc'), self.config.get('config', 'uuid'))
        data = None
        params = self.SuperEncrypt( self.getAllInfo() )
        try:
            r = requests.post(url, data = params, verify = False)
            r.raise_for_status()
            self.logger.info("Heartbeat sent")
            data = r.content.decode('utf8')
        except requests.exceptions.ConnectionError as e:
            self.logger.error("Could not retrieve data: %s" % e)
        except requests.exceptions.HTTPError as e:
            self.logger.error("Could not retrieve data: %s" % e)

        return data


    def disableTimeSync(self):
        result = self.cmd("timedatectl set-ntp false")
        return result

    def setDate(self, data):
        cmd = "date --set='%s'" % data
        result = self.cmd(cmd)
        return result

    def run(self):
        if '-d' in sys.argv:
            self.logger.info('Daemonize mode..')
            self.run = True
            while self.run:
                try:
                    date = json.loads(self.SendHeartbeat())['timestamp']
                    self.disableTimeSync()
                    self.setDate(date)
                except KeyboardInterrupt as e:
                    self.run = False
                    return
                time.sleep(int(self.config.get('config', 'beaconing_period')))
        else:
            date = json.loads(self.SendHeartbeat())['timestamp']
            self.disableTimeSync()
            self.setDate(date)

if __name__ == '__main__':
    k = HoneyAgent()
    k.run()
