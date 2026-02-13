chiamogna.sqlite3:
	mysql_dump_to_sqlite.py --sqlite3 chiamogna.sqlite3 --mysql-dump-file backup_10_Gen_2026.sql

chiamogna.sqlite3.schema:
	sqlite3 chiamogna.sqlite3 ".schema" > chiamogna.sqlite3.schema

import_log:
	../manage.py import_chiamogna
