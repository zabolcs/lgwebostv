'use strict';

const assert = require('assert');
const core = require('../common/url-core');

function allowed(input, normalized) {
  assert.strictEqual(core.isAllowed(input), true, input);
  assert.strictEqual(core.normalize(input), normalized || input, input);
}

function denied(input, code) {
  assert.strictEqual(core.isAllowed(input), false, input);
  assert.throws(
    () => core.parse(input),
    error => error && error.name === 'UrlPolicyError' && (!code || error.code === code),
    input
  );
}

allowed('http://192.168.0.125:8080/live');
allowed('https://10.0.0.8/camera.m3u8?camera=front&quality=high');
allowed('http://172.16.0.1', 'http://172.16.0.1/');
allowed('http://172.31.255.254:65535/path?empty=&flag');
allowed('https://192.168.255.254/image.webp?label=access-tokenized');

denied('', 'EMPTY');
denied(null, 'TYPE');
denied('ftp://192.168.0.125/file', 'FORMAT');
denied('http://camera.local/live', 'HOST');
denied('http://localhost/live', 'HOST');
denied('http://127.0.0.1/live', 'PRIVATE_IPV4');
denied('http://8.8.8.8/live', 'PRIVATE_IPV4');
denied('http://172.15.0.1/live', 'PRIVATE_IPV4');
denied('http://172.32.0.1/live', 'PRIVATE_IPV4');
denied('http://[fd00::1]/live', 'HOST');
denied('http://192.168.0.100/live', 'FORBIDDEN_HOST');
denied('http://192.168.1.10/proxy/192.168.0.100/live', 'FORBIDDEN_REFERENCE');
denied('http://192.168.1.10/live?src=192.168.0.100', 'FORBIDDEN_REFERENCE');
denied('http://192.168.1.10/proxy/192.168.000.100/live', 'FORBIDDEN_REFERENCE');
denied('http://192.168.1.10/proxy/0192.168.0.100/live', 'FORBIDDEN_REFERENCE');
denied('http://192.168.1.10/proxy/3232235620/live', 'FORBIDDEN_REFERENCE');
denied('http://192.168.1.10/proxy/0xc0a80064/live', 'FORBIDDEN_REFERENCE');
denied('http://192.168.1.10/proxy/192.168.100/live', 'FORBIDDEN_REFERENCE');
denied('http://192.168.1.10/proxy/192.11010148/live', 'FORBIDDEN_REFERENCE');
denied('http://192.168.1.10/proxy/0xc0.0xa8.0x0.0x64/live', 'FORBIDDEN_REFERENCE');
denied('http://192.168.1.10/proxy/0000300.0000250.0000.0000144/live', 'FORBIDDEN_REFERENCE');
denied('http://192.168.1.10/proxy/0000000000300.0000000000250.00000000000.0000000000144/live', 'FORBIDDEN_REFERENCE');
denied('http://192.168.1.10/%252e%252e/admin', 'ENCODING');
denied('http://192.168.1.10/live?%2574oken=x', 'ENCODING');
denied('http://192.168.1.0/live', 'NETWORK_ADDRESS');
denied('http://192.168.1.255/live', 'NETWORK_ADDRESS');
denied('http://user:pass@192.168.0.125/live', 'USERINFO');
denied('http://192.168.0.125/live#preview', 'FRAGMENT');
denied('http://192.168.0.125:0/live', 'PORT');
denied('http://192.168.0.125:65536/live', 'PORT');
denied('http://192.168.0.125:080/live', 'PORT');
denied('http://192.168.000.125/live', 'PRIVATE_IPV4');
denied('http://192.168.0.125/live stream', 'WHITESPACE');
denied('http://192.168.0.125\\@example.com/live', 'BACKSLASH');

denied('http://192.168.0.125/live?token=secret', 'SENSITIVE_QUERY');
denied('http://192.168.0.125/live?ACCESS_TOKEN=secret', 'SENSITIVE_QUERY');
denied('http://192.168.0.125/live?access%5Ftoken=secret', 'ENCODING');
denied('http://192.168.0.125/live?password=secret', 'SENSITIVE_QUERY');
denied('http://192.168.0.125/live?auth=bearer', 'SENSITIVE_QUERY');
denied('http://192.168.0.125/live?api_key=secret', 'SENSITIVE_QUERY');
denied('http://192.168.0.125/live?x-signature=value', 'SENSITIVE_QUERY');
denied('http://192.168.0.125/live?token%5B%5D=secret', 'ENCODING');
denied('http://192.168.0.125/live?bad%ZZ=value', 'ENCODING');

console.log('url core tests: PASS');
