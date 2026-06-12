"""
图索引模块
实现实体和关系的键值对结构 (K,V)
K: 索引键（简短词汇或短语）
V: 详细描述段落（包含相关文本片段）
"""
from collections import defaultdict
import json
from dataclasses import dataclass, field
from typing import List, Any, Dict
from gustobot.infrastructure.core.logger import get_logger

logger = get_logger(service="GraphIndexingModule")

@dataclass
class EntityKeyValue:
    """实体键值对"""
    entity_name: str
    index_keys: List[str]
    content_value: str
    entity_type: str
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class RelationKeyValue:
    """关系键值对"""
    relation_id: str
    index_keys: List[str]
    content_value: str
    relation_type: str
    source_entity: str
    target_entity: str
    metadata: Dict[str, Any] = field(default_factory=dict)

class GraphIndexingModule:
    """
    图索引模块
    核心功能：
    1. 为实体创建键值对（名称作为唯一索引键）
    2. 为关系创建键值对（多个索引键，包含全局主题）
    3. 去重和优化图操作
    4. 支持增量更新
    """
    
    def __init__(self, config, llm_client):
        self.config = config
        self.llm_client = llm_client

        self.entities_kv_store: Dict[str, EntityKeyValue] = {}
        self.relations_kv_store: Dict[str, RelationKeyValue] = {}

        self.key_to_entities: Dict[str, List[str]] = defaultdict(list)
        self.key_to_relations: Dict[str, List[str]] = defaultdict(list)

    @staticmethod
    def _get_value(item: Any, key: str, default: Any = None) -> Any:
        """兼容字典和对象属性访问。"""
        if isinstance(item, dict):
            return item.get(key, default)
        return getattr(item, key, default)

    def _generate_relation_index_keys(self,source_entity: EntityKeyValue, target_entity: EntityKeyValue, relation_type: str) -> List[str]:
        """
        为关系生成多个索引键，包含全局主题
        """
        keys = [relation_type]

         # 根据关系类型和实体类型生成主题键
        if relation_type == "REQUIRES":
            # 菜谱-食材关系的主题键
            keys.extend([
                "食材搭配",
                "烹饪原料",
                f"{source_entity.entity_name}_食材",
                target_entity.entity_name
            ])
        elif relation_type == "HAS_STEP":
            # 菜谱-步骤关系的主题键
            keys.extend([
                "制作步骤",
                "烹饪过程",
                f"{source_entity.entity_name}_步骤",
                "制作方法"
            ])
        elif relation_type == "BELONGS_TO_CATEGORY":
            # 分类关系的主题键
            keys.extend([
                "菜品分类",
                "美食类别",
                target_entity.entity_name
            ])
        
        if getattr(self.config, "enable_llm", False):
            llm_keys = self._llm_enhance_relation_keys(source_entity, target_entity, relation_type)
            keys.extend(llm_keys)

        return list(set(keys))  # 去重
        

    def _llm_enhance_relation_keys(self,source_entity: EntityKeyValue, target_entity: EntityKeyValue, relation_type: str) -> List[str]:
        """
        使用LLM增强关系索引键，生成全局主题
        """
        prompt = f"""
        分析以下实体关系，生成相关的主题关键词：
        
        源实体: {source_entity.entity_name} ({source_entity.entity_type})
        目标实体: {target_entity.entity_name} ({target_entity.entity_type})
        关系类型: {relation_type}
        
        请生成3-5个相关的主题关键词，用于索引和检索。
        返回JSON格式：{{"keywords": ["关键词1", "关键词2", "关键词3"]}}
        """
        try:
            logger.info(f"调用LLM增强关系索引键，关系类型：{relation_type}，源实体：{source_entity.entity_name}，目标实体：{target_entity.entity_name}")

            response = self.llm_client.chat.completions.create(
                model=self.config.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1, # 越大越随机，越小越确定
                max_tokens=200
            )

            raw_content = response.choices[0].message.content.strip()
            # 去除 LLM 可能返回的 Markdown 代码块标记
            if raw_content.startswith("```"):
                raw_content = raw_content.split("\n", 1)[-1]
                raw_content = raw_content.rsplit("```", 1)[0]
            result = json.loads(raw_content)
            keys = result.get("keywords", [])

            logger.info(f"LLM生成的关系索引键：{keys}")
            return keys
        except Exception as e:
            logger.error(f"LLM增强关系索引键失败: {e}")
            return []
        

    def _rebuild_key_mappings(self):
        """重建键到实体/关系的映射"""
        self.key_to_entities = defaultdict(list)
        self.key_to_relations = defaultdict(list)

        for entity_id, entity in self.entities_kv_store.items():
            for key in entity.index_keys:
                self.key_to_entities[key].append(entity_id)
        
        for rel_id, relation in self.relations_kv_store.items():
            for key in relation.index_keys:
                self.key_to_relations[key].append(rel_id)

    def create_entity_key_values(self, recipes: List[Any], ingredients: List[Any], 
                                cooking_steps: List[Any]) -> Dict[str, EntityKeyValue]:
        """
        为实体创建键值对结构
        每个实体使用其名称作为唯一索引键
        """
        logger.info("开始创建实体键值对...")
        # 处理食谱
        for recipe in recipes:
            node_id = self._get_value(recipe, "node_id")
            name = self._get_value(recipe, "name") or f"菜谱_{node_id}"

            content_parts = [f"菜谱名称：{name}"]
            prop = self._get_value(recipe, "properties", {}) or {}
            if prop:
                if prop.get("description"):
                    content_parts.append(f"描述：{prop['description']}")
                if prop.get("category"):
                    content_parts.append(f"类别：{prop['category']}")
                if prop.get("cuisineType"):
                    content_parts.append(f"菜系：{prop['cuisineType']}")
                if prop.get("difficulty"):
                    content_parts.append(f"难度：{prop['difficulty']}")
                if prop.get("cooking_time"):
                    content_parts.append(f"烹饪时间：{prop['cooking_time']}分钟")

            content = "\n".join(content_parts)

            entity = EntityKeyValue(
                entity_name=name,
                index_keys=[name],
                content_value=content,
                entity_type="recipe",
                metadata={
                    "node_id": node_id,
                    "properties": prop
                }
            )

            self.entities_kv_store[node_id] = entity
            self.key_to_entities[name].append(node_id)

        # 处理食材
        for ingredient in ingredients:
            node_id = self._get_value(ingredient, "node_id")
            name = self._get_value(ingredient, "name") or f"食材_{node_id}"

            content_parts = [f"食材名称：{name}"]
            prop = self._get_value(ingredient, "properties", {}) or {}
            if prop:
                if prop.get("category"):
                    content_parts.append(f"类别：{prop['category']}")
                if prop.get("nutrition"):
                    content_parts.append(f"营养信息：{prop['nutrition']}")
                if prop.get("storage"):
                    content_parts.append(f"存储方式：{prop['storage']}")

            content = "\n".join(content_parts)

            entity = EntityKeyValue(
                entity_name=name,
                index_keys=[name],
                content_value=content,
                entity_type="ingredient",
                metadata={
                    "node_id": node_id,
                    "properties": prop
                }
            )

            self.entities_kv_store[node_id] = entity
            self.key_to_entities[name].append(node_id)

        # 处理烹饪步骤
        for step in cooking_steps:
            node_id = self._get_value(step, "node_id")
            name = self._get_value(step, "name") or f"烹饪步骤_{node_id}"

            content_parts = [f"烹饪步骤：{name}"]
            prop = self._get_value(step, "properties", {}) or {}
            if prop:
                if prop.get("description"):
                    content_parts.append(f"步骤描述：{prop['description']}")
                if prop.get("order"):
                    content_parts.append(f"步骤顺序：{prop['order']}")
                if prop.get("technique"):
                    content_parts.append(f"技巧：{prop['technique']}")
                if prop.get("time"):
                    content_parts.append(f"时间：{prop['time']}")

            content = "\n".join(content_parts)

            entity = EntityKeyValue(
                entity_name=name,
                index_keys=[name],
                content_value=content,
                entity_type="cooking_step",
                metadata={
                    "node_id": node_id,
                    "properties": prop
                }
            )

            self.entities_kv_store[node_id] = entity
            self.key_to_entities[name].append(node_id)
        
        logger.info(f"完成创建实体键值对，当前实体数量：{len(self.entities_kv_store)}")
        return self.entities_kv_store


    def create_relation_key_values(self,relations: List[Any]) -> Dict[str, RelationKeyValue]:
        """
        为关系创建键值对结构
        关系可能有多个索引键，包含从LLM增强的全局主题
        """
        logger.info("开始创建关系键值对...")

        for idx, (start_id, end_id, relation_type) in enumerate(relations):
            relation_id = f"relation_{idx}_{start_id}_{end_id}"

            start_entity = self.entities_kv_store.get(start_id)
            end_entity = self.entities_kv_store.get(end_id)

            if not start_entity or not end_entity:
                logger.warning(f"关系 {relation_id} 的起始或结束实体不存在，跳过")
                continue
            

            content_parts = [
                f"关系类型：{relation_type}",
                f"源实体：{start_entity.entity_name}（类型：{start_entity.entity_type}）",
                f"目标实体：{end_entity.entity_name}（类型：{end_entity.entity_type}）"
            ]
            content = "\n".join(content_parts)

            index_keys = self._generate_relation_index_keys(start_entity, end_entity, relation_type)

            relation = RelationKeyValue(
                    relation_id=relation_id,
                    index_keys=index_keys,
                    content_value=content,
                    relation_type=relation_type,
                    source_entity=start_entity.entity_name,
                    target_entity=end_entity.entity_name,
                    metadata={
                        "source_name": start_entity.entity_name,
                        "target_name": end_entity.entity_name,
                        "created_from_graph": True
                    }
                )

            self.relations_kv_store[relation_id] = relation

            for key in index_keys:
                self.key_to_relations[key].append(relation_id)

        return self.relations_kv_store
        

    def deduplicate_entities_and_relations(self):
        """
        去重相同的实体和关系，一个实体或关系可能有多个索引id键，但内容相同只保留一个
        """
        logger.info("开始去重实体和关系...")

        entity_to_id = defaultdict(list)
        for entity_id, entity in self.entities_kv_store.items():
            entity_to_id[entity.entity_name].append(entity_id)

        duplicate_entities = []
        for entity_name, ids in entity_to_id.items():
            if len(ids) > 1:
                primary_id = ids[0]
                primary_entity = self.entities_kv_store[primary_id]
                for duplicate_id in ids[1:]:
                    duplicate_entity = self.entities_kv_store[duplicate_id]
                    primary_entity.content_value += f"\n\n 补充信息：{duplicate_entity.content_value}"
                    duplicate_entities.append(duplicate_id)

        for duplicate_id in duplicate_entities:
            del self.entities_kv_store[duplicate_id]
            logger.info(f"去除重复实体：{duplicate_id}")

        relation_to_id = defaultdict(list)
        for rel_id, relation in self.relations_kv_store.items():
            signature = f"{relation.source_entity}_{relation.target_entity}_{relation.relation_type}"
            relation_to_id[signature].append(rel_id)

        duplicate_relations = []
        for signature, ids in relation_to_id.items():
            if len(ids) > 1:
                duplicate_relations.extend(ids[1:])

        for duplicate_id in duplicate_relations:
            del self.relations_kv_store[duplicate_id]
            logger.info(f"去除重复关系：{duplicate_id}")

        self._rebuild_key_mappings()
        logger.info(f"去重完成 - 删除了 {len(duplicate_entities)} 个重复实体，{len(duplicate_relations)} 个重复关系")
    

    def get_entities_by_key(self, key: str) -> List[EntityKeyValue]:
        """根据索引键获取实体"""
        entity_ids = self.key_to_entities.get(key, [])
        return [self.entities_kv_store[eid] for eid in entity_ids if eid in self.entities_kv_store]
        
    
    def get_relations_by_key(self, key: str) -> List[RelationKeyValue]:
        """根据索引键获取关系"""
        relation_ids = self.key_to_relations.get(key, [])
        return [self.relations_kv_store[rid] for rid in relation_ids if rid in self.relations_kv_store]

    
    def get_statistics(self):
        """获取键值对存储统计信息"""
        return {
            "total_entities": len(self.entities_kv_store),
            "total_relations": len(self.relations_kv_store),
            "total_entity_keys": sum(len(kv.index_keys) for kv in self.entities_kv_store.values()),
            "total_relation_keys": sum(len(kv.index_keys) for kv in self.relations_kv_store.values()),
            "entity_types": {
                "Recipe": len([kv for kv in self.entities_kv_store.values() if kv.entity_type == "Recipe"]),
                "Ingredient": len([kv for kv in self.entities_kv_store.values() if kv.entity_type == "Ingredient"]),
                "CookingStep": len([kv for kv in self.entities_kv_store.values() if kv.entity_type == "CookingStep"])
            }
        } 
