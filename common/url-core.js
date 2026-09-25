(function (root, factory) {
  'use strict';
  var api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.WebOsPipUrlCore = api;
}(typeof window !== 'undefined' ? window : this, function () {
  'use strict';

  var FORBIDDEN_HOST = '192.168.0.100';
  var SENSITIVE_NAMES = {
    token: true,
    access_token: true,
    password: true,
    auth: true,
    key: true,
    signature: true
  };

  function PolicyError(code, message) {
    this.name = 'UrlPolicyError';
    this.code = code;
    this.message = message;
    if (Error.captureStackTrace) Error.captureStackTrace(this, PolicyError);
  }
  PolicyError.prototype = Object.create(Error.prototype);
  PolicyError.prototype.constructor = PolicyError;

  function fail(code, message) {
    throw new PolicyError(code, message);
  }

  function parseIPv4(text) {
    if (!/^\d{1,3}(?:\.\d{1,3}){3}$/.test(text)) return null;
    var raw = text.split('.');
    var octets = [];
    for (var i = 0; i < raw.length; i += 1) {
      var value = Number(raw[i]);
      if (value < 0 || value > 255 || String(value) !== raw[i]) return null;
      octets.push(value);
    }
    return octets;
  }

  function isPrivate(octets) {
    return octets[0] === 10 ||
      (octets[0] === 172 && octets[1] >= 16 && octets[1] <= 31) ||
      (octets[0] === 192 && octets[1] === 168);
  }

  function containsForbiddenAddress(value) {
    var text = String(value || '');
    if (/(^|[^0-9])(?:[0-9]+\.){1,3}[0-9]+([^0-9]|$)/.test(text)) return true;
    if (/0x/i.test(text)) return true;
    return /0x0*c0a80064|0*3232235620|0*30052000144/i.test(text);
  }

  function sensitiveQueryName(rawName) {
    var decoded;
    try {
      decoded = decodeURIComponent(String(rawName || '').replace(/\+/g, ' '));
    } catch (error) {
      fail('QUERY_ENCODING', 'A query parameternév hibásan kódolt.');
    }
    if (/[\u0000-\u001f\u007f]/.test(decoded)) {
      fail('QUERY_NAME', 'A query paraméternév vezérlőkaraktert tartalmaz.');
    }
    var name = decoded.toLowerCase();
    if (SENSITIVE_NAMES[name]) return true;
    var parts = name.split(/[^a-z0-9]+/);
    for (var i = 0; i < parts.length; i += 1) {
      if (SENSITIVE_NAMES[parts[i]]) return true;
    }
    return false;
  }

  function validateQuery(query) {
    if (!query) return;
    var fields = query.split('&');
    for (var i = 0; i < fields.length; i += 1) {
      if (!fields[i]) continue;
      var equals = fields[i].indexOf('=');
      var name = equals === -1 ? fields[i] : fields[i].slice(0, equals);
      if (sensitiveQueryName(name)) {
        fail('SENSITIVE_QUERY', 'Titkot hordozó query paraméternév nem engedélyezett.');
      }
    }
  }

  function parse(input) {
    if (typeof input !== 'string') fail('TYPE', 'Az URL szöveg legyen.');
    var text = input.trim();
    if (!text) fail('EMPTY', 'Az URL nem lehet üres.');
    if (/[\u0000-\u0020\u007f]/.test(text)) fail('WHITESPACE', 'Az URL nem tartalmazhat szóközt vagy vezérlőkaraktert.');
    if (text.indexOf('#') !== -1) fail('FRAGMENT', 'URL-fragment nem engedélyezett.');
    if (text.indexOf('\\') !== -1) fail('BACKSLASH', 'A backslash nem engedélyezett az URL-ben.');
    if (text.indexOf('%') !== -1) fail('ENCODING', 'Kódolt URL-rész nem engedélyezett.');

    var match = /^(https?):\/\/([^\/?#]+)(\/[^?#]*)?(?:\?([^#]*))?$/i.exec(text);
    if (!match) fail('FORMAT', 'Csak teljes http/https URL engedélyezett.');
    var scheme = match[1].toLowerCase();
    var authority = match[2];
    if (authority.indexOf('@') !== -1) fail('USERINFO', 'URL userinfo nem engedélyezett.');

    var authorityMatch = /^(\d{1,3}(?:\.\d{1,3}){3})(?::(\d{1,5}))?$/.exec(authority);
    if (!authorityMatch) fail('HOST', 'Csak numerikus IPv4-cím engedélyezett; DNS-név és IPv6 nem.');
    var host = authorityMatch[1];
    var octets = parseIPv4(host);
    if (!octets || !isPrivate(octets)) fail('PRIVATE_IPV4', 'Csak RFC1918 privát IPv4-cím engedélyezett.');
    host = octets.join('.');
    if (host === FORBIDDEN_HOST) fail('FORBIDDEN_HOST', 'Ez a helyi cím biztonsági okból tiltott.');
    if (octets[3] === 0 || octets[3] === 255) fail('NETWORK_ADDRESS', 'Hálózati vagy broadcast cím nem engedélyezett.');

    var port = null;
    if (authorityMatch[2] !== undefined) {
      port = Number(authorityMatch[2]);
      if (!Number.isInteger(port) || port < 1 || port > 65535 || String(port) !== authorityMatch[2]) {
        fail('PORT', 'A port 1 és 65535 közötti kanonikus egész szám legyen.');
      }
    }

    var path = match[3] || '/';
    var query = match[4] === undefined ? '' : match[4];
    if (path.indexOf(':') !== -1 || path.indexOf('@') !== -1) {
      fail('PATH_SYNTAX', 'Proxy-célt jelölő kettőspont vagy kukacjel nem engedélyezett az útvonalban.');
    }
    if (containsForbiddenAddress(path) || containsForbiddenAddress(query)) {
      fail('FORBIDDEN_REFERENCE', 'A tiltott helyi cím útvonalban vagy queryben sem használható.');
    }
    var segments = path.split('/');
    for (var segmentIndex = 0; segmentIndex < segments.length; segmentIndex += 1) {
      if (segments[segmentIndex] === '.' || segments[segmentIndex] === '..') {
        fail('DOT_SEGMENT', 'Dot-segment nem engedélyezett.');
      }
    }
    validateQuery(query);
    var normalized = scheme + '://' + host + (port === null ? '' : ':' + port) + path +
      (match[4] === undefined ? '' : '?' + query);
    return {
      scheme: scheme,
      host: host,
      port: port,
      path: path,
      query: query,
      url: normalized
    };
  }

  function normalize(input) {
    return parse(input).url;
  }

  function isAllowed(input) {
    try {
      parse(input);
      return true;
    } catch (error) {
      return false;
    }
  }

  return {
    PolicyError: PolicyError,
    forbiddenHost: FORBIDDEN_HOST,
    containsForbiddenAddress: containsForbiddenAddress,
    parse: parse,
    normalize: normalize,
    isAllowed: isAllowed
  };
}));
