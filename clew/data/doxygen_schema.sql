-- SPDX-License-Identifier: MIT
--
-- Doxygen's OWN schema, captured verbatim from a real build (doxygen 1.9.8,
-- sqlite3 output). For a C/C++/Python repo, these are the only tables clew
-- does not create itself — they are the only ones the synthetic `rich_db`
-- test fixture (tests/richdb.py) has to hand-make. For a Rust repo, doxygen
-- never runs at all: clew/rustdoc.py loads this SAME schema and populates
-- `path`/`refid`/`memberdef` from rustdoc's JSON output instead, so every
-- downstream stage sees an identically-shaped database regardless of which
-- front end produced it.
--
-- Dumped rather than retyped, and dumped WHOLE (tables + indexes + the eight
-- convenience views) for one reason: the fixture's table set is compared against
-- a real build in tests/integration/test_fixture_fidelity.py, and a fixture that
-- carries a hand-abridged doxygen schema would differ from reality in exactly the
-- places nobody thought to check. Regenerate with:
--
--   sqlite3 <a real clew.db> \
--     "SELECT sql || ';' FROM sqlite_master
--       WHERE tbl_name IN ('compounddef','compoundref','contains','includes',
--                          'member','memberdef','memberdef_param','meta','param',
--                          'path','refid','reimplements','xrefs')
--          OR type = 'view'
--       ORDER BY CASE type WHEN 'table' THEN 0 WHEN 'index' THEN 1 ELSE 2 END, name;"
--
-- DO NOT hand-edit: any divergence from what doxygen emits is a fixture that
-- describes a database no build produces.
CREATE TABLE compounddef (
	-- Class/struct definitions.
	rowid                INTEGER PRIMARY KEY NOT NULL,
	name                 TEXT NOT NULL,
	title                TEXT,
	kind                 TEXT NOT NULL, -- 'category' 'class' 'constants' 'dir' 'enum' 'example' 'exception' 'file' 'group' 'interface' 'library' 'module' 'namespace' 'package' 'page' 'protocol' 'service' 'singleton' 'struct' 'type' 'union' 'unknown' ''
	prot                 INTEGER,
	file_id              INTEGER NOT NULL REFERENCES path,
	line                 INTEGER NOT NULL,
	column               INTEGER NOT NULL,
	header_id            INTEGER REFERENCES path,
	detaileddescription  TEXT,
	briefdescription     TEXT,
	FOREIGN KEY (rowid) REFERENCES refid (rowid)
);
CREATE TABLE compoundref (
	-- Inheritance relation.
	rowid          INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
	base_rowid     INTEGER NOT NULL REFERENCES compounddef,
	derived_rowid  INTEGER NOT NULL REFERENCES compounddef,
	prot           INTEGER NOT NULL,
	virt           INTEGER NOT NULL,
	UNIQUE(base_rowid, derived_rowid)
);
CREATE TABLE contains (
	-- inner/outer relations (file, namespace, dir, class, group, page)
	rowid        INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
	inner_rowid  INTEGER NOT NULL REFERENCES compounddef,
	outer_rowid  INTEGER NOT NULL REFERENCES compounddef
);
CREATE TABLE includes (
	-- #include relations.
	rowid        INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
	local        INTEGER NOT NULL,
	src_id       INTEGER NOT NULL REFERENCES path, -- File id of the includer.
	dst_id       INTEGER NOT NULL REFERENCES path, -- File id of the includee.
	UNIQUE(local, src_id, dst_id) ON CONFLICT IGNORE
);
CREATE TABLE member (
	-- Memberdef <-> containing compound relation.
	-- Similar to XML listofallmembers.
	rowid            INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
	scope_rowid      INTEGER NOT NULL REFERENCES compounddef,
	memberdef_rowid  INTEGER NOT NULL REFERENCES memberdef,
	prot             INTEGER NOT NULL,
	virt             INTEGER NOT NULL,
	UNIQUE(scope_rowid, memberdef_rowid)
);
CREATE TABLE memberdef (
	-- All processed identifiers.
	rowid                INTEGER PRIMARY KEY NOT NULL,
	name                 TEXT NOT NULL,
	definition           TEXT,
	type                 TEXT,
	argsstring           TEXT,
	scope                TEXT,
	initializer          TEXT,
	bitfield             TEXT,
	read                 TEXT,
	write                TEXT,
	prot                 INTEGER DEFAULT 0, -- 0:public 1:protected 2:private 3:package
	static               INTEGER DEFAULT 0, -- 0:no 1:yes
	extern               INTEGER DEFAULT 0, -- 0:no 1:yes
	const                INTEGER DEFAULT 0, -- 0:no 1:yes
	explicit             INTEGER DEFAULT 0, -- 0:no 1:yes
	inline               INTEGER DEFAULT 0, -- 0:no 1:yes 2:both (set after encountering inline and not-inline)
	final                INTEGER DEFAULT 0, -- 0:no 1:yes
	sealed               INTEGER DEFAULT 0, -- 0:no 1:yes
	new                  INTEGER DEFAULT 0, -- 0:no 1:yes
	optional             INTEGER DEFAULT 0, -- 0:no 1:yes
	required             INTEGER DEFAULT 0, -- 0:no 1:yes
	volatile             INTEGER DEFAULT 0, -- 0:no 1:yes
	virt                 INTEGER DEFAULT 0, -- 0:no 1:virtual 2:pure-virtual
	mutable              INTEGER DEFAULT 0, -- 0:no 1:yes
	initonly             INTEGER DEFAULT 0, -- 0:no 1:yes
	attribute            INTEGER DEFAULT 0, -- 0:no 1:yes
	property             INTEGER DEFAULT 0, -- 0:no 1:yes
	readonly             INTEGER DEFAULT 0, -- 0:no 1:yes
	bound                INTEGER DEFAULT 0, -- 0:no 1:yes
	constrained          INTEGER DEFAULT 0, -- 0:no 1:yes
	transient            INTEGER DEFAULT 0, -- 0:no 1:yes
	maybevoid            INTEGER DEFAULT 0, -- 0:no 1:yes
	maybedefault         INTEGER DEFAULT 0, -- 0:no 1:yes
	maybeambiguous       INTEGER DEFAULT 0, -- 0:no 1:yes
	readable             INTEGER DEFAULT 0, -- 0:no 1:yes
	writable             INTEGER DEFAULT 0, -- 0:no 1:yes
	gettable             INTEGER DEFAULT 0, -- 0:no 1:yes
	privategettable      INTEGER DEFAULT 0, -- 0:no 1:yes
	protectedgettable    INTEGER DEFAULT 0, -- 0:no 1:yes
	settable             INTEGER DEFAULT 0, -- 0:no 1:yes
	privatesettable      INTEGER DEFAULT 0, -- 0:no 1:yes
	protectedsettable    INTEGER DEFAULT 0, -- 0:no 1:yes
	accessor             INTEGER DEFAULT 0, -- 0:no 1:assign 2:copy 3:retain 4:string 5:weak
	addable              INTEGER DEFAULT 0, -- 0:no 1:yes
	removable            INTEGER DEFAULT 0, -- 0:no 1:yes
	raisable             INTEGER DEFAULT 0, -- 0:no 1:yes
	kind                 TEXT NOT NULL, -- 'macro definition' 'function' 'variable' 'typedef' 'enumeration' 'enumvalue' 'signal' 'slot' 'friend' 'dcop' 'property' 'event' 'interface' 'service'
	bodystart            INTEGER DEFAULT 0, -- starting line of definition
	bodyend              INTEGER DEFAULT 0, -- ending line of definition
	bodyfile_id          INTEGER REFERENCES path, -- file of definition
	file_id              INTEGER NOT NULL REFERENCES path,  -- file where this identifier is located
	line                 INTEGER NOT NULL,  -- line where this identifier is located
	column               INTEGER NOT NULL,  -- column where this identifier is located
	detaileddescription  TEXT,
	briefdescription     TEXT,
	inbodydescription    TEXT,
	FOREIGN KEY (rowid) REFERENCES refid (rowid)
);
CREATE TABLE memberdef_param (
	-- Junction table for memberdef parameters.
	rowid        INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
	memberdef_id INTEGER NOT NULL REFERENCES memberdef,
	param_id     INTEGER NOT NULL REFERENCES param
);
CREATE TABLE meta (
	-- Information about this db and how it was generated.
	-- Doxygen info
	doxygen_version    TEXT PRIMARY KEY NOT NULL,
	schema_version     TEXT NOT NULL, -- Schema-specific semver
	-- run info
	generated_at       TEXT NOT NULL,
	generated_on       TEXT NOT NULL,
	-- project info
	project_name       TEXT NOT NULL,
	project_number     TEXT,
	project_brief      TEXT
);
CREATE TABLE param (
	-- All processed parameters.
	rowid        INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
	attributes   TEXT,
	type         TEXT,
	declname     TEXT,
	defname      TEXT,
	array        TEXT,
	defval       TEXT,
	briefdescription TEXT
);
CREATE TABLE path (
	-- Paths of source files and includes.
	rowid        INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
	type         INTEGER NOT NULL, -- 1:file 2:dir
	local        INTEGER NOT NULL,
	found        INTEGER NOT NULL,
	name         TEXT NOT NULL
);
CREATE TABLE refid (
	-- Distinct refid for all documented entities.
	rowid        INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
	refid        TEXT NOT NULL UNIQUE
);
CREATE TABLE reimplements (
	-- Inherited member reimplementation relations.
	rowid                  INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
	memberdef_rowid        INTEGER NOT NULL REFERENCES memberdef, -- reimplementing memberdef id.
	reimplemented_rowid    INTEGER NOT NULL REFERENCES memberdef, -- reimplemented memberdef id.
	UNIQUE(memberdef_rowid, reimplemented_rowid) ON CONFLICT IGNORE
);
CREATE TABLE xrefs (
	-- Cross-reference relation
	-- (combines xml <referencedby> and <references> nodes).
	rowid        INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
	src_rowid    INTEGER NOT NULL REFERENCES refid, -- referrer id.
	dst_rowid    INTEGER NOT NULL REFERENCES refid, -- referee id.
	context      TEXT NOT NULL, -- inline, argument, initializer
	-- Just need to know they link; ignore duplicates.
	UNIQUE(src_rowid, dst_rowid, context) ON CONFLICT IGNORE
);
CREATE UNIQUE INDEX idx_param ON param
	(type, defname);







CREATE VIEW argument_xrefs (
	-- Crossrefs from member def/decl arguments
	rowid,
	src_rowid,
	dst_rowid
)
as SELECT 
	xrefs.rowid,
	xrefs.src_rowid,
	xrefs.dst_rowid
FROM xrefs WHERE xrefs.context='argument';
CREATE VIEW def (
	-- Combined summary of all -def types for easier joins.
	rowid,
	refid,
	kind,
	name,
	summary)
as SELECT 
	refid.rowid,
	refid.refid,
	memberdef.kind,
	memberdef.name,
	memberdef.briefdescription 
FROM refid 
JOIN memberdef ON refid.rowid=memberdef.rowid 
UNION ALL 
SELECT 
	refid.rowid,
	refid.refid,
	compounddef.kind,
	compounddef.name,
	CASE 
		WHEN briefdescription IS NOT NULL 
		THEN briefdescription 
		ELSE title 
	END summary
FROM refid 
JOIN compounddef ON refid.rowid=compounddef.rowid;
CREATE VIEW external_file (
	-- File paths outside the project (found or not).
	rowid,
	found,
	name
)
as SELECT 
	path.rowid,
	path.found,
	path.name
FROM path WHERE path.type=1 AND path.local=0;
CREATE VIEW initializer_xrefs (
	-- Crossrefs from member initializers
	rowid,
	src_rowid,
	dst_rowid
)
as SELECT 
	xrefs.rowid,
	xrefs.src_rowid,
	xrefs.dst_rowid
FROM xrefs WHERE xrefs.context='initializer';
CREATE VIEW inline_xrefs (
	-- Crossrefs from inline member source.
	rowid,
	src_rowid,
	dst_rowid
)
as SELECT 
	xrefs.rowid,
	xrefs.src_rowid,
	xrefs.dst_rowid
FROM xrefs WHERE xrefs.context='inline';
CREATE VIEW inner_outer
	-- Joins 'contains' relations to simplify inner/outer 'rel' queries.
as SELECT 
	inner.*,
	outer.*
FROM def as inner
	JOIN contains ON inner.rowid=contains.inner_rowid
	JOIN def AS outer ON outer.rowid=contains.outer_rowid;
CREATE VIEW local_file (
	-- File paths found within the project.
	rowid,
	found,
	name
)
as SELECT 
	path.rowid,
	path.found,
	path.name
FROM path WHERE path.type=1 AND path.local=1 AND path.found=1;
CREATE VIEW rel (
	-- Boolean indicator of relations available for a given entity.
	-- Join to (compound-|member-)def to find fetch-worthy relations.
	rowid,
	reimplemented,
	reimplements,
	innercompounds,
	outercompounds,
	innerpages,
	outerpages,
	innerdirs,
	outerdirs,
	innerfiles,
	outerfiles,
	innerclasses,
	outerclasses,
	innernamespaces,
	outernamespaces,
	innergroups,
	outergroups,
	members,
	compounds,
	subclasses,
	superclasses,
	links_in,
	links_out,
	argument_links_in,
	argument_links_out,
	initializer_links_in,
	initializer_links_out
)
as SELECT 
	def.rowid,
	EXISTS (SELECT rowid FROM reimplements WHERE reimplemented_rowid=def.rowid),
	EXISTS (SELECT rowid FROM reimplements WHERE memberdef_rowid=def.rowid),
	-- rowid/kind for inner, [rowid:1/kind:1] for outer
	EXISTS (SELECT * FROM inner_outer WHERE [rowid:1]=def.rowid),
	EXISTS (SELECT * FROM inner_outer WHERE rowid=def.rowid),
	EXISTS (SELECT * FROM inner_outer WHERE [rowid:1]=def.rowid AND kind='page'),
	EXISTS (SELECT * FROM inner_outer WHERE rowid=def.rowid AND [kind:1]='page'),
	EXISTS (SELECT * FROM inner_outer WHERE [rowid:1]=def.rowid AND kind='dir'),
	EXISTS (SELECT * FROM inner_outer WHERE rowid=def.rowid AND [kind:1]='dir'),
	EXISTS (SELECT * FROM inner_outer WHERE [rowid:1]=def.rowid AND kind='file'),
	EXISTS (SELECT * FROM inner_outer WHERE rowid=def.rowid AND [kind:1]='file'),
	EXISTS (SELECT * FROM inner_outer WHERE [rowid:1]=def.rowid AND kind in (
'category','class','enum','exception','interface','module','protocol',
'service','singleton','struct','type','union'
)),
	EXISTS (SELECT * FROM inner_outer WHERE rowid=def.rowid AND [kind:1] in (
'category','class','enum','exception','interface','module','protocol',
'service','singleton','struct','type','union'
)),
	EXISTS (SELECT * FROM inner_outer WHERE [rowid:1]=def.rowid AND kind='namespace'),
	EXISTS (SELECT * FROM inner_outer WHERE rowid=def.rowid AND [kind:1]='namespace'),
	EXISTS (SELECT * FROM inner_outer WHERE [rowid:1]=def.rowid AND kind='group'),
	EXISTS (SELECT * FROM inner_outer WHERE rowid=def.rowid AND [kind:1]='group'),
	EXISTS (SELECT rowid FROM member WHERE scope_rowid=def.rowid),
	EXISTS (SELECT rowid FROM member WHERE memberdef_rowid=def.rowid),
	EXISTS (SELECT rowid FROM compoundref WHERE base_rowid=def.rowid),
	EXISTS (SELECT rowid FROM compoundref WHERE derived_rowid=def.rowid),
	EXISTS (SELECT rowid FROM inline_xrefs WHERE dst_rowid=def.rowid),
	EXISTS (SELECT rowid FROM inline_xrefs WHERE src_rowid=def.rowid),
	EXISTS (SELECT rowid FROM argument_xrefs WHERE dst_rowid=def.rowid),
	EXISTS (SELECT rowid FROM argument_xrefs WHERE src_rowid=def.rowid),
	EXISTS (SELECT rowid FROM initializer_xrefs WHERE dst_rowid=def.rowid),
	EXISTS (SELECT rowid FROM initializer_xrefs WHERE src_rowid=def.rowid)
FROM def ORDER BY def.rowid;
