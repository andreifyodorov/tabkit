Changes
=======

0.9
---
	* Change SyslogStream to LogStream. Use LogStream(logging.handlers.SysLogHandler(), ...) to achieve the same.
	  (Reason: syslog.syslog() uses libc syslog() which limits message to 2048 chars under FreeBSD)

0.8
---
	* Fix boolean values parsing

0.7
---
	* DataDesc add

0.6
---
	* SyslogStream

0.5
---
    * Fix unicode string writes

0.4
---
    * StrictWriter now allows None values.

0.3
---
    * tjoin - perform the join operation on two files.

0.2
---

    * utils.parse_file(stream, strict=False, data_desc=None)
    * utils.Writer(fh, data_desc, strict=False)
    * tpretty - output FILE(s) as human-readable pretty table.
    * PEP8ize source code
