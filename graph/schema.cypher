// 建库脚本：约束与索引。负责人：P2。必须可重复执行（全部 IF NOT EXISTS）。
// 用法：cat graph/schema.cypher | cypher-shell -u neo4j -p <password>
// 或 python scripts/build_graph.py --schema

CREATE CONSTRAINT person_name_unique IF NOT EXISTS
FOR (p:Person) REQUIRE p.name IS UNIQUE;

CREATE CONSTRAINT faction_name_unique IF NOT EXISTS
FOR (f:Faction) REQUIRE f.name IS UNIQUE;

CREATE CONSTRAINT event_name_unique IF NOT EXISTS
FOR (e:Event) REQUIRE e.name IS UNIQUE;

CREATE CONSTRAINT place_name_unique IF NOT EXISTS
FOR (pl:Place) REQUIRE pl.name IS UNIQUE;

CREATE CONSTRAINT chapter_no_unique IF NOT EXISTS
FOR (c:Chapter) REQUIRE c.no IS UNIQUE;

// 常用过滤字段索引
CREATE INDEX person_faction_idx IF NOT EXISTS
FOR (p:Person) ON (p.faction);

CREATE INDEX event_year_idx IF NOT EXISTS
FOR (e:Event) ON (e.year);

// 自检：执行后应看到 5 条约束 + 2 条索引
SHOW CONSTRAINTS;
SHOW INDEXES;
