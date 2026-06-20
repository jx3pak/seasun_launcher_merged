#!/usr/bin/env python3
import hashlib
import http.server
import json
import re
import urllib.request
import urllib.error
import urllib.parse
import sys
import socket
import zstd

cache = {}
last = [0, None, None]
host_tw = 'https://xlauncherv2hk.amazingseasuncdn.com'
host_cn = 'https://xlauncherv2qq.xoyocdn.com'

class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.proxy_request('GET')
    
    def do_POST(self):
        self.proxy_request('POST')
    
    def do_PUT(self):
        self.proxy_request('PUT')
    
    def do_DELETE(self):
        self.proxy_request('DELETE')
    
    def do_PATCH(self):
        self.proxy_request('PATCH')
    
    def do_HEAD(self):
        self.proxy_request('HEAD')
    
    def do_OPTIONS(self):
        self.proxy_request('OPTIONS')

    def real_get(self, headers, url):
        req = urllib.request.Request(url, headers=headers, data=b'', method="GET")
        sys.stderr.write(f"[remote] {url}\n")
        resp =  urllib.request.urlopen(req)
        content = resp.read()
        return content

    def merge_seasun_config(self, my_host, target_headers):
        t1, a1, b1 = last
        if not a1 or not b1 or time.time() - last[0] > 60:
            a1 = self.real_get(target_headers, host_cn + "/Release/SeasunConfigs/zh_CN/SeasunGame.remote.checksum")
            b1 = self.real_get(target_headers, host_tw + "/Release/SeasunConfigs/zh_TW/SeasunGame.remote.checksum")
        k = a1+b1
        if not k in cache:
            a2 = self.real_get(target_headers, host_cn + "/Release/SeasunConfigs/zh_CN/SeasunGame_%s.remote" % a1.decode("utf8"))
            b2 = self.real_get(target_headers, host_tw + "/Release/SeasunConfigs/zh_TW/SeasunGame_%s.remote" % b1.decode("utf8"))
            a3 = zstd.decompress(a2)
            b3 = zstd.decompress(b2)
            a4 = json.loads(a3)
            b4 = json.loads(b3)
            a4['GameLibrary'] = b4['GameLibrary'] + a4['GameLibrary']
            a4['Url']['GameConfigUrls'] = ['http://%s/Release/GameConfigs/' % my_host]
            cache[k] = zstd.compress(json.dumps(a4, indent=4).encode("utf8"))
        return cache[k]

    def proxy_request(self, method):
        try:
            my_host = self.headers.get('host')
            path = self.path.split("?")[0]
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length) if content_length > 0 else None
            target_headers = self.filter_headers(self.headers)
            if re.match('/Release/SeasunConfigs/\\w+/SeasunGame.remote.checksum', path):
                data = self.merge_seasun_config(my_host, target_headers)
                data_md5 = hashlib.md5(data).hexdigest().encode("utf8")
                self.send_response(200)
                self.send_header('content-encoding', '32')
                self.end_headers()
                self.wfile.write(data_md5)
                return
            if re.match('/Release/SeasunConfigs/\\w+/SeasunGame_\\w{32}.remote', path):
                data = self.merge_seasun_config(my_host, target_headers)
                self.send_response(200)
                self.send_header('content-encoding', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            if path.startswith('/Release/GameConfigs/'):
                if path.startswith('/Release/GameConfigs/JX3_TW/'):
                    target_url = host_tw + path
                else:
                    target_url = host_cn + path
                sys.stderr.write(f"[remote] {target_url}\n")
                req = urllib.request.Request(
                    target_url,
                    data=body,
                    headers=target_headers,
                    method=method
                )
                with urllib.request.urlopen(req, timeout=30) as response:
                    self.send_response(response.status)
                    response_headers = self.filter_response_headers(response.headers)
                    for key, value in response_headers.items():
                        self.send_header(key, value)
                    self.end_headers()
                    self.wfile.write(response.read())
                return
            self.send_response(404)
            self.end_headers()
            return


        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            response_headers = self.filter_response_headers(e.headers)
            for key, value in response_headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(e.read())
            
        except Exception as e:
            self.send_error(502, f"Proxy Error: {str(e)}")
    
    def filter_headers(self, headers):
        hop_by_hop = {
            'connection', 'keep-alive', 'proxy-authenticate',
            'proxy-authorization', 'te', 'trailers',
            'transfer-encoding', 'upgrade', 'proxy-connection',
            'host', 'range'
        }
        
        filtered = {}
        for key, value in headers.items():
            if key.lower() not in hop_by_hop:
                filtered[key] = value
        
        return filtered
    
    def filter_response_headers(self, headers):
        hop_by_hop = {
            'connection', 'keep-alive', 'proxy-authenticate',
            'proxy-authorization', 'te', 'trailers',
            'transfer-encoding', 'upgrade'
        }
        filtered = {}
        for key, value in headers.items():
            if key.lower() not in hop_by_hop:
                filtered[key] = value
        return filtered
    
    def log_message(self, format, *args):
        sys.stderr.write(f"[{self.log_date_time_string()}] "
                        f"{self.client_address[0]} - {format % args}\n")


if __name__ == '__main__':
    port = 8000
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    server = http.server.HTTPServer(("0.0.0.0", port), ProxyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
