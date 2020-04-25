import usocket

class Response:

    def __init__(self, socket, stream):
        self.socket = socket
        self.stream = stream
        self.encoding = "utf-8"
        self._cached = None

    def close(self):
        if self.stream:
            self.stream.close()
            self.stream = None
        if self.socket:
            self.socket.close()
            self.socket = None

    @property
    def content(self):
        if self._cached is None:
            try:
                self._cached = self.stream.read()
            finally:
                # OSError: [Errno -76] MBEDTLS_ERR_NET_RECV_FAILED
                # AttributeError: NoneType object has no attribute close
                # https://forum.pycom.io/topic/5755/micropython-error-trail-confusing-me
                self.close()
        return self._cached

    @property
    def text(self):
        return str(self.content, self.encoding)

    def json(self):
        import ujson
        return ujson.loads(self.content)


def request(method, url, data=None, json=None, headers={}, stream=None, parse_headers=True):
    redir_cnt = 1
    if json is not None:
        assert data is None
        import ujson
        data = ujson.dumps(json).encode()

    while True:
        try:
            proto, dummy, host, path = url.split("/", 3)
        except ValueError:
            proto, dummy, host = url.split("/", 2)
            path = ""
        if proto == "http:":
            port = 80
        elif proto == "https:":
            import ussl
            port = 443
        else:
            raise ValueError("Unsupported protocol: " + proto)

        if ":" in host:
            host, port = host.split(":", 1)
            port = int(port)

        ai = usocket.getaddrinfo(host, port, 0, usocket.SOCK_STREAM)
        ai = ai[0]

        resp_d = None
        if parse_headers is not False:
            resp_d = {}

        s = usocket.socket(ai[0], ai[1], ai[2])
        try:
            s.connect(ai[-1])
            if proto == "https:":
                s = ussl.wrap_socket(s, server_hostname=host)

            try:
                ss = s.makefile("rwb", 0)
            except ValueError:
                # Pycom's "socket.makefile" doesn't accept the "r" mode.
                # https://forum.pycom.io/topic/4625/simple-http-server
                ss = s.makefile("wb", 0)

            ss.write(b"%s /%s HTTP/1.0\r\n" % (method.encode(), path.encode()))
            if not "Host" in headers:
                ss.write(b"Host: %s:%s\r\n" % (host.encode(), str(port).encode()))
            # Iterate over keys to avoid tuple alloc
            for k in headers:
                ss.write(k.encode())
                ss.write(b": ")
                ss.write(headers[k].encode())
                ss.write(b"\r\n")
            if json is not None:
                ss.write(b"Content-Type: application/json\r\n")
            if data:
                ss.write(b"Content-Length: %d\r\n" % len(data))
            ss.write(b"Connection: close\r\n\r\n")
            if data:
                ss.write(data)

            l = ss.readline()
            #print(l)
            l = l.split(None, 2)
            status = int(l[1])
            reason = ""
            if len(l) > 2:
                reason = l[2].rstrip()
            while True:
                l = ss.readline()
                if not l or l == b"\r\n":
                    break
                #print(l)

                if l.startswith(b"Transfer-Encoding:"):
                    if b"chunked" in l:
                        raise ValueError("Unsupported " + l.decode())
                elif l.startswith(b"Location:") and 300 <= status <= 399:
                    if not redir_cnt:
                        raise ValueError("Too many redirects")
                    redir_cnt -= 1
                    url = l[9:].decode().strip()
                    #print("redir to:", url)
                    status = 300
                    break

                if parse_headers is False:
                    pass
                elif parse_headers is True:
                    l = l.decode()
                    k, v = l.split(":", 1)
                    resp_d[k] = v.strip()
                else:
                    parse_headers(l, resp_d)
        except OSError:
            s.close()
            raise

        if status != 300:
            break

    resp = Response(s, ss)
    resp.status_code = status
    resp.reason = reason
    if resp_d is not None:
        resp.headers = resp_d
    return resp


def head(url, **kw):
    return request("HEAD", url, **kw)

def get(url, **kw):
    return request("GET", url, **kw)

def post(url, **kw):
    return request("POST", url, **kw)

def put(url, **kw):
    return request("PUT", url, **kw)

def patch(url, **kw):
    return request("PATCH", url, **kw)

def delete(url, **kw):
    return request("DELETE", url, **kw)
