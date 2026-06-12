
// Neo4j 数据导入脚本

// 导入节点
LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row
CREATE (n:Concept)
SET n.nodeId = row.nodeId,
    n.name = row.name,
    n.preferredTerm = row.preferredTerm,
    n.category = row.category,
    n.conceptType = row.conceptType,
    n.difficulty = toInteger(row.difficulty),
    n.cuisineType = row.cuisineType,
    n.prepTime = row.prepTime,
    n.cookTime = row.cookTime,
    n.servings = row.servings,
    n.tags = row.tags,
    n.filePath = row.filePath,
    n.amount = row.amount,
    n.unit = row.unit,
    n.isMain = toBoolean(row.isMain),
    n.description = row.description,
    n.stepNumber = toInteger(row.stepNumber),
    n.methods = row.methods,
    n.tools = row.tools,
    n.timeEstimate = row.timeEstimate;

// 创建索引
CREATE INDEX concept_id_index IF NOT EXISTS FOR (c:Concept) ON (c.nodeId);
CREATE INDEX concept_name_index IF NOT EXISTS FOR (c:Concept) ON (c.name);
CREATE INDEX concept_category_index IF NOT EXISTS FOR (c:Concept) ON (c.category);

// 导入关系
LOAD CSV WITH HEADERS FROM 'file:///relationships.csv' AS row
MATCH (start:Concept {nodeId: row.startNodeId})
MATCH (end:Concept {nodeId: row.endNodeId})
CALL apoc.create.relationship(start, row.relationshipType, {
    relationshipId: row.relationshipId,
    amount: row.amount,
    unit: row.unit,
    stepOrder: toInteger(row.step_order)
}, end) YIELD rel
RETURN count(rel);
