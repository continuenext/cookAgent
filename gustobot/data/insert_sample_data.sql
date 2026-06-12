-- GustoBot 示例数据种子文件
-- 基于 gustobot/data/recipes/ 中实际 Markdown 菜谱生成
-- 需在 init_mysql.sql 之后执行

USE recipe_db;
SET NAMES utf8mb4;

-- ═══════════════════════════════════════════════
-- 1. 菜系 (cuisines)
-- ═══════════════════════════════════════════════
INSERT INTO cuisines (name, cooking_style, typical_tools) VALUES
('川菜',   '以麻辣鲜香为主，善用花椒辣椒，注重小炒爆炒',     JSON_ARRAY('炒锅', '菜刀')),
('粤菜',   '注重食材原味，清淡鲜美，讲究蒸制与火候',         JSON_ARRAY('蒸锅', '炒锅')),
('家常菜', '取材广泛做法质朴，偏重炖煮煎炸，口味因地而异',   JSON_ARRAY('炒锅', '汤锅')),
('东北菜', '分量扎实，酱香浓郁，善用炖煮与酱制',             JSON_ARRAY('炒锅', '砂锅')),
('甜品',   '烘焙或冷藏制作，注重温度与配比精确',             JSON_ARRAY('烤箱', '打蛋器')),
('汤粥',   '以水为基底，慢煮或快煮提取食材精华',             JSON_ARRAY('汤锅', '砂锅')),
('凉菜',   '无需加热或仅焯水拌制，清爽开胃',                 JSON_ARRAY('菜刀', '拌盆')),
('早餐',   '快手简便，注重营养搭配与省时操作',               JSON_ARRAY('平底锅', '微波炉')),
('饮品',   '调制或熬煮，注重配比口感与温度控制',             JSON_ARRAY('汤锅', '量杯')),
('主食',   '以米面为基底，炒煎煮蒸等多种方式',               JSON_ARRAY('炒锅', '电饭煲'));

-- ═══════════════════════════════════════════════
-- 2. 厨具 (cooking_tools)
-- ═══════════════════════════════════════════════
INSERT INTO cooking_tools (name, type, material, capacity) VALUES
('炒锅',     'pan',   '铁/不锈钢',   '32cm'),
('平底锅',   'pan',   '不粘涂层',    '28cm'),
('汤锅',     'pot',   '不锈钢',      '5L'),
('蒸锅',     'pot',   '不锈钢',      '28cm'),
('砂锅',     'pot',   '陶瓷',        '3L'),
('菜刀',     'knife', '不锈钢',      '8寸'),
('水果刀',   'knife', '不锈钢',       NULL),
('烤箱',     'oven',  '电热',        '30L'),
('打蛋器',   'other', '不锈钢/电动',  NULL),
('刮刀',     'other', '硅胶',         NULL),
('模具',     'other', '铝合金阳极',   '6/8寸'),
('砧板',     'other', '竹',          '40cm'),
('锅铲',     'other', '不锈钢',       NULL),
('电饭煲',   'other', '复合材质',     '3L'),
('微波炉',   'oven',  '电磁加热',     NULL);

-- ═══════════════════════════════════════════════
-- 3. 食材 (ingredients)
-- ═══════════════════════════════════════════════
INSERT INTO ingredients (name, category, calories, protein, carbs, fat, storage_method, shelf_life) VALUES
-- 肉类
('鸡胸肉',     '肉类',   165.00, 31.00,  0.00,  3.60, '冷冻保存', 90),
('五花肉',     '肉类',   395.00, 13.20,  0.00, 37.00, '冷冻保存', 90),
('排骨',       '肉类',   264.00, 18.30,  0.00, 20.40, '冷冻保存', 90),
('肉糜',       '肉类',   220.00, 17.00,  0.00, 15.00, '冷冻保存', 30),
('火腿肠',     '肉类',   212.00, 10.00, 10.00, 15.00, '常温保存', 180),
-- 蔬菜
('大葱',       '蔬菜',    30.00,  1.60,  6.50,  0.30, '阴凉通风', 14),
('蒜苗',       '蔬菜',    40.00,  2.10,  7.20,  0.40, '冷藏保存', 5),
('青红椒',     '蔬菜',    23.00,  1.00,  5.30,  0.10, '冷藏保存', 7),
('菠菜',       '蔬菜',    23.00,  2.90,  3.60,  0.40, '冷藏保存', 3),
('西兰花',     '蔬菜',    34.00,  3.70,  6.60,  0.40, '冷藏保存', 5),
('西红柿',     '蔬菜',    18.00,  0.90,  3.90,  0.20, '常温阴凉', 5),
('洋葱',       '蔬菜',    40.00,  1.10,  9.30,  0.10, '阴凉通风', 30),
('黄瓜',       '蔬菜',    15.00,  0.70,  3.60,  0.10, '冷藏保存', 5),
('胡萝卜',     '蔬菜',    41.00,  0.90, 10.00,  0.20, '冷藏保存', 10),
('玉米粒',     '蔬菜',    86.00,  3.20, 19.00,  1.20, '冷藏保存', 4),
('生菜',       '蔬菜',    16.00,  1.30,  2.90,  0.20, '冷藏保存', 3),
-- 豆制品
('内脂豆腐',   '豆制品',  47.00,  5.00,  2.70,  1.90, '冷藏保存', 5),
-- 水产
('鲈鱼',       '水产',    97.00, 18.00,  0.00,  2.60, '冷藏保存', 2),
('活虾',       '水产',    87.00, 18.30,  0.00,  0.80, '鲜活保存', 1),
-- 蛋奶
('鸡蛋',       '蛋奶',   143.00, 12.60,  1.30, 10.60, '冷藏保存', 30),
('牛奶',       '蛋奶',    54.00,  3.00,  3.40,  3.20, '冷藏保存', 7),
-- 谷物/干货
('面粉',       '谷物',   366.00, 10.00, 75.00,  1.20, '阴凉干燥', 180),
('低筋面粉',   '谷物',   354.00,  8.50, 75.20,  1.30, '阴凉干燥', 180),
('冷饭',       '谷物',   116.00,  2.60, 25.90,  0.30, '冷藏保存', 2),
('速冻饺子',   '谷物',   215.00,  8.00, 30.00,  7.00, '冷冻保存', 90),
('熟花生',     '干果',   563.00, 25.80, 16.10, 44.20, '阴凉干燥', 90),
('松子仁',     '干果',   673.00, 13.70,  9.30, 68.40, '冷藏保存', 60),
-- 中药/特殊材料
('乌梅',       '干货',   292.00,  1.50, 64.00,  1.50, '阴凉干燥', 365),
('乌枣',       '干货',   264.00,  3.70, 67.50,  0.50, '阴凉干燥', 365),
('山楂片',     '干货',    95.00,  0.50, 25.10,  0.60, '阴凉干燥', 365),
('干桂花',     '干货',   288.00,  0.60, 62.00,  4.50, '阴凉干燥', 365),
-- 调料
('生抽',       '调料',    60.00,  8.00,  6.00,  0.10, '阴凉避光', 365),
('老抽',       '调料',    72.00,  5.00, 11.40,  0.10, '阴凉避光', 365),
('料酒',       '调料',    52.00,  0.40,  4.60,  0.10, '阴凉避光', 365),
('香醋',       '调料',    68.00,  0.10,  4.90,  0.00, '阴凉避光', 365),
('白砂糖',     '调料',   387.00,  0.00,100.00,  0.00, '常温密封', 720),
('冰糖',       '调料',   397.00,  0.00, 99.30,  0.00, '常温密封', 720),
('食盐',       '调料',     0.00,  0.00,  0.00,  0.00, '常温干燥', 365),
('食用油',     '调料',   884.00,  0.00,  0.00,100.00, '阴凉避光', 365),
('蚝油',       '调料',    72.00,  5.00, 12.00,  1.00, '冷藏保存', 180),
('蒸鱼豉油',   '调料',    72.00,  6.00, 10.00,  0.00, '阴凉避光', 365),
('芝麻油',     '调料',   898.00,  0.00,  0.00, 99.70, '阴凉避光', 365),
('豆瓣酱',     '调料',   185.00,  6.00, 20.00,  8.00, '阴凉避光', 365),
('蒜蓉辣酱',   '调料',   118.00,  2.00, 18.00,  4.50, '冷藏保存', 365),
('干辣椒',     '调料',   318.00, 12.00, 56.00, 17.00, '阴凉干燥', 365),
('花椒',       '调料',   285.00, 10.00, 30.00, 16.00, '阴凉干燥', 365),
('番茄酱',     '调料',    80.00,  1.60, 18.90,  0.10, '冷藏保存', 180),
('五香粉',     '调料',   195.00,  7.50, 40.00,  3.50, '常温密封', 365),
('淀粉',       '调料',   381.00,  0.00, 91.00,  0.10, '阴凉干燥', 365),
('香叶',       '调料',   313.00,  8.00, 49.00,  8.40, '阴凉干燥', 365),
('八角',       '调料',   337.00, 14.00, 35.00, 16.00, '阴凉干燥', 365),
('胡椒粉',     '调料',   255.00, 10.00, 64.00,  3.00, '常温密封', 365),
('鸡精',       '调料',   210.00, 25.00, 11.00,  1.00, '常温密封', 720),
('黄冰糖',     '调料',   397.00,  0.00, 99.30,  0.00, '常温密封', 720),
('甘草',       '调料',   166.00,  6.00, 35.00,  0.50, '阴凉干燥', 365),
('陈皮',       '调料',   155.00,  8.00, 30.00,  1.40, '阴凉干燥', 365),
('咸鸭蛋',     '调料',   190.00, 12.70,  3.10, 14.70, '冷藏保存', 30),
('酱油',       '调料',    60.00,  8.00,  6.00,  0.10, '阴凉避光', 365),
('芝麻',       '调料',   578.00, 17.70, 23.50, 49.70, '阴凉干燥', 365);

-- ═══════════════════════════════════════════════
-- 缓存 ID 变量
-- ═══════════════════════════════════════════════
SELECT id INTO @c_sichuan   FROM cuisines WHERE name = '川菜';
SELECT id INTO @c_cantonese FROM cuisines WHERE name = '粤菜';
SELECT id INTO @c_home      FROM cuisines WHERE name = '家常菜';
SELECT id INTO @c_dongbei   FROM cuisines WHERE name = '东北菜';
SELECT id INTO @c_dessert   FROM cuisines WHERE name = '甜品';
SELECT id INTO @c_soup      FROM cuisines WHERE name = '汤粥';
SELECT id INTO @c_cold      FROM cuisines WHERE name = '凉菜';
SELECT id INTO @c_breakfast FROM cuisines WHERE name = '早餐';
SELECT id INTO @c_drink     FROM cuisines WHERE name = '饮品';
SELECT id INTO @c_staple    FROM cuisines WHERE name = '主食';

SELECT id INTO @t_wok       FROM cooking_tools WHERE name = '炒锅';
SELECT id INTO @t_flatpan   FROM cooking_tools WHERE name = '平底锅';
SELECT id INTO @t_stockpot  FROM cooking_tools WHERE name = '汤锅';
SELECT id INTO @t_steamer   FROM cooking_tools WHERE name = '蒸锅';
SELECT id INTO @t_casserole FROM cooking_tools WHERE name = '砂锅';
SELECT id INTO @t_knife     FROM cooking_tools WHERE name = '菜刀';
SELECT id INTO @t_fruitknife FROM cooking_tools WHERE name = '水果刀';
SELECT id INTO @t_oven      FROM cooking_tools WHERE name = '烤箱';
SELECT id INTO @t_whisk     FROM cooking_tools WHERE name = '打蛋器';
SELECT id INTO @t_scraper   FROM cooking_tools WHERE name = '刮刀';
SELECT id INTO @t_mold      FROM cooking_tools WHERE name = '模具';
SELECT id INTO @t_board     FROM cooking_tools WHERE name = '砧板';
SELECT id INTO @t_spatula   FROM cooking_tools WHERE name = '锅铲';
SELECT id INTO @t_ricecooker FROM cooking_tools WHERE name = '电饭煲';
SELECT id INTO @t_microwave FROM cooking_tools WHERE name = '微波炉';

SELECT id INTO @i_chicken   FROM ingredients WHERE name = '鸡胸肉';
SELECT id INTO @i_pork      FROM ingredients WHERE name = '五花肉';
SELECT id INTO @i_ribs      FROM ingredients WHERE name = '排骨';
SELECT id INTO @i_mince     FROM ingredients WHERE name = '肉糜';
SELECT id INTO @i_ham       FROM ingredients WHERE name = '火腿肠';
SELECT id INTO @i_scallion  FROM ingredients WHERE name = '大葱';
SELECT id INTO @i_garlic_sprout FROM ingredients WHERE name = '蒜苗';
SELECT id INTO @i_pepper    FROM ingredients WHERE name = '青红椒';
SELECT id INTO @i_spinach   FROM ingredients WHERE name = '菠菜';
SELECT id INTO @i_broccoli  FROM ingredients WHERE name = '西兰花';
SELECT id INTO @i_tomato    FROM ingredients WHERE name = '西红柿';
SELECT id INTO @i_onion     FROM ingredients WHERE name = '洋葱';
SELECT id INTO @i_cucumber  FROM ingredients WHERE name = '黄瓜';
SELECT id INTO @i_carrot    FROM ingredients WHERE name = '胡萝卜';
SELECT id INTO @i_corn      FROM ingredients WHERE name = '玉米粒';
SELECT id INTO @i_lettuce   FROM ingredients WHERE name = '生菜';
SELECT id INTO @i_tofu      FROM ingredients WHERE name = '内脂豆腐';
SELECT id INTO @i_bass      FROM ingredients WHERE name = '鲈鱼';
SELECT id INTO @i_shrimp    FROM ingredients WHERE name = '活虾';
SELECT id INTO @i_egg       FROM ingredients WHERE name = '鸡蛋';
SELECT id INTO @i_milk      FROM ingredients WHERE name = '牛奶';
SELECT id INTO @i_flour     FROM ingredients WHERE name = '面粉';
SELECT id INTO @i_lowflour  FROM ingredients WHERE name = '低筋面粉';
SELECT id INTO @i_rice      FROM ingredients WHERE name = '冷饭';
SELECT id INTO @i_dumpling  FROM ingredients WHERE name = '速冻饺子';
SELECT id INTO @i_peanut    FROM ingredients WHERE name = '熟花生';
SELECT id INTO @i_pinenuts  FROM ingredients WHERE name = '松子仁';
SELECT id INTO @i_wumei     FROM ingredients WHERE name = '乌梅';
SELECT id INTO @i_wuzao     FROM ingredients WHERE name = '乌枣';
SELECT id INTO @i_hawthorn  FROM ingredients WHERE name = '山楂片';
SELECT id INTO @i_guihua    FROM ingredients WHERE name = '干桂花';
SELECT id INTO @i_soysauce  FROM ingredients WHERE name = '生抽';
SELECT id INTO @i_darksoy   FROM ingredients WHERE name = '老抽';
SELECT id INTO @i_shaoxing  FROM ingredients WHERE name = '料酒';
SELECT id INTO @i_vinegar   FROM ingredients WHERE name = '香醋';
SELECT id INTO @i_sugar     FROM ingredients WHERE name = '白砂糖';
SELECT id INTO @i_rocksugar FROM ingredients WHERE name = '冰糖';
SELECT id INTO @i_salt      FROM ingredients WHERE name = '食盐';
SELECT id INTO @i_oil       FROM ingredients WHERE name = '食用油';
SELECT id INTO @i_oystersauce FROM ingredients WHERE name = '蚝油';
SELECT id INTO @i_steamingsauce FROM ingredients WHERE name = '蒸鱼豉油';
SELECT id INTO @i_sesameoil FROM ingredients WHERE name = '芝麻油';
SELECT id INTO @i_douban    FROM ingredients WHERE name = '豆瓣酱';
SELECT id INTO @i_garlic_chili FROM ingredients WHERE name = '蒜蓉辣酱';
SELECT id INTO @i_driedchili FROM ingredients WHERE name = '干辣椒';
SELECT id INTO @i_sichuan_pepper FROM ingredients WHERE name = '花椒';
SELECT id INTO @i_ketchup   FROM ingredients WHERE name = '番茄酱';
SELECT id INTO @i_fivespice FROM ingredients WHERE name = '五香粉';
SELECT id INTO @i_starch    FROM ingredients WHERE name = '淀粉';
SELECT id INTO @i_bayleaf   FROM ingredients WHERE name = '香叶';
SELECT id INTO @i_staranise FROM ingredients WHERE name = '八角';
SELECT id INTO @i_whitepep  FROM ingredients WHERE name = '胡椒粉';
SELECT id INTO @i_msgsub    FROM ingredients WHERE name = '鸡精';
SELECT id INTO @i_y_rocksugar FROM ingredients WHERE name = '黄冰糖';
SELECT id INTO @i_licorice  FROM ingredients WHERE name = '甘草';
SELECT id INTO @i_chenpi    FROM ingredients WHERE name = '陈皮';
SELECT id INTO @i_saltedegg FROM ingredients WHERE name = '咸鸭蛋';
SELECT id INTO @i_soy       FROM ingredients WHERE name = '酱油';
SELECT id INTO @i_sesame    FROM ingredients WHERE name = '芝麻';

START TRANSACTION;

-- ═══════════════════════════════════════════════
-- 4. 菜谱 + 步骤 + 食材关联 + 工具关联
-- ═══════════════════════════════════════════════

-- -----------------------------------------------
-- Recipe 1: 宫保鸡丁 (★★★★ 川菜)
-- -----------------------------------------------
INSERT INTO recipes (name, description, total_time, servings, difficulty, cuisine_id, total_calories)
VALUES ('宫保鸡丁', '老派川菜的简单做法，鸡丁配花生与干辣椒，酸甜微辣', 90, 2, 'hard', @c_sichuan, 520.00);
SET @r := LAST_INSERT_ID();

INSERT INTO recipe_steps (recipe_id, step_number, action, instruction, duration, temperature, tools_used, tips)
VALUES
(@r, 1, '切丁腌制', '鸡肉去骨切1.5cm丁加盐老抽料酒淀粉搅匀，取葱绿姜片泡开水备用，冰箱腌制1小时', 60, '常温', JSON_ARRAY('砧板','菜刀','搅拌碗'), '鸡丁大小尽量一致便于受热均匀'),
(@r, 2, '焙干辣椒', '干辣椒切段小火焙至微糊，花椒焙出香味捞起备用', 3, '小火', JSON_ARRAY('炒锅'), '辣椒不停翻动避免炒糊'),
(@r, 3, '煎鸡丁', '大火倒油七成热下鸡丁，煎至两面变色', 3, '大火', JSON_ARRAY('炒锅','锅铲'), '竹筷子起泡即七成热'),
(@r, 4, '焖煮收汁', '下葱粒加葱姜水焖2分钟，下花生辣椒花椒加鸡精香醋白糖，水淀粉勾芡收汁淋芝麻油', 5, '大火→中小火', JSON_ARRAY('炒锅','锅铲'), '调味汁提前兑好快速翻炒');
SET @s1_1 := LAST_INSERT_ID();
SET @s1_2 := @s1_1 + 1;
SET @s1_3 := @s1_1 + 2;
SET @s1_4 := @s1_1 + 3;

INSERT INTO step_tools (step_id, tool_id, `usage`) VALUES
(@s1_1, @t_board, '切丁'), (@s1_1, @t_knife, '切丁'),
(@s1_2, @t_wok, '焙制'),
(@s1_3, @t_wok, '煎制'), (@s1_3, @t_spatula, '翻面'),
(@s1_4, @t_wok, '收汁'), (@s1_4, @t_spatula, '翻炒');

INSERT INTO recipe_ingredients (recipe_id, ingredient_id, quantity, unit, prep_method, prep_time, is_main, adjusted_calories, ingredient_type) VALUES
(@r, @i_chicken,  '350', 'g',  '切丁腌制', 60, 1, 577.50, 'main'),
(@r, @i_peanut,   '150', 'g',  '焙干备用',  5, 0, 844.50, 'auxiliary'),
(@r, @i_scallion, '180', 'g',  '切段切粒',  3, 0,  54.00, 'auxiliary'),
(@r, @i_driedchili,'10', 'g',  '切段焙干',  3, 0,  31.80, 'seasoning'),
(@r, @i_sichuan_pepper,'5','g','焙干备用',   2, 0,  14.25, 'seasoning'),
(@r, @i_soysauce, '10', 'g',  '调味',       0, 0,   6.00, 'seasoning'),
(@r, @i_vinegar,  '5',  'ml', '调汁',       0, 0,   3.40, 'seasoning'),
(@r, @i_sugar,    '2',  'g',  '调汁',       0, 0,   7.74, 'seasoning'),
(@r, @i_shaoxing, '15', 'ml', '腌制',       0, 0,   7.80, 'seasoning'),
(@r, @i_starch,   '25', 'g',  '腌制+勾芡',  0, 0,  95.25, 'seasoning'),
(@r, @i_oil,      '20', 'g',  '烹饪用油',   0, 0, 176.80, 'seasoning'),
(@r, @i_sesameoil,'10', 'ml', '出锅淋入',   0, 0,  89.80, 'seasoning');

-- -----------------------------------------------
-- Recipe 2: 麻婆豆腐 (★★★ 川菜)
-- -----------------------------------------------
INSERT INTO recipes (name, description, total_time, servings, difficulty, cuisine_id, total_calories)
VALUES ('麻婆豆腐', '参考麻婆豆腐创作，富含微量元素，非常下饭', 30, 2, 'medium', @c_sichuan, 320.00);
SET @r := LAST_INSERT_ID();

INSERT INTO recipe_steps (recipe_id, step_number, action, instruction, duration, temperature, tools_used, tips)
VALUES
(@r, 1, '准备食材', '蒜姜切碎小米辣切圈，肉糜加盐和酱油腌制，豆腐用水果刀切2.5cm块', 10, '常温', JSON_ARRAY('菜刀','水果刀'), '咸鸭蛋去蛋黄只用蛋白捣碎'),
(@r, 2, '炒香料', '小火放油炒蒜姜辣椒花椒咸鸭蛋蒜蓉辣酱20秒', 1, '小火', JSON_ARRAY('炒锅','锅铲'), '小火慢炒出香味'),
(@r, 3, '炒肉放豆腐', '中火炒肉糜变色，小火放入豆腐撒盐酱油，锅边倒开水没过豆腐', 3, '中火→小火', JSON_ARRAY('炒锅'), '从锅边倒水不然豆腐容易破'),
(@r, 4, '收汁入味', '大火煮沸转中火，等水剩1/5且豆腐入色关火盛盘', 10, '大火→中火', JSON_ARRAY('炒锅'), '注意观察防止糊锅');
SET @s2_1 := LAST_INSERT_ID();

INSERT INTO step_tools (step_id, tool_id, `usage`) VALUES
(@s2_1, @t_knife, '切碎'), (@s2_1, @t_fruitknife, '切豆腐'),
(@s2_1+1, @t_wok, '炒制'), (@s2_1+1, @t_spatula, '翻炒'),
(@s2_1+2, @t_wok, '炒煮'),
(@s2_1+3, @t_wok, '收汁');

INSERT INTO recipe_ingredients (recipe_id, ingredient_id, quantity, unit, prep_method, prep_time, is_main, adjusted_calories, ingredient_type) VALUES
(@r, @i_tofu,      '1',  '盒', '切块',       2, 1, 47.00, 'main'),
(@r, @i_mince,     '25', 'g',  '腌制',       5, 0, 55.00, 'auxiliary'),
(@r, @i_saltedegg, '1',  '枚', '去黄取白捣碎', 3, 0, 95.00, 'auxiliary'),
(@r, @i_sichuan_pepper,'20','颗','备用',      0, 0,  5.70, 'seasoning'),
(@r, @i_garlic_chili,'5','g',  '直接用',      0, 0,  5.90, 'seasoning'),
(@r, @i_soy,       '10', 'g',  '调味',       0, 0,  6.00, 'seasoning'),
(@r, @i_salt,      '3',  'g',  '调味',       0, 0,  0.00, 'seasoning'),
(@r, @i_oil,       '15', 'ml', '烹饪用油',   0, 0,132.60, 'seasoning');

-- -----------------------------------------------
-- Recipe 3: 简易红烧肉 (★★★ 家常菜)
-- -----------------------------------------------
INSERT INTO recipes (name, description, total_time, servings, difficulty, cuisine_id, total_calories)
VALUES ('简易红烧肉', '新手不败菜谱，香糯无敌棒色泽诱人肥而不腻，建议搭配米饭', 70, 3, 'medium', @c_home, 1800.00);
SET @r := LAST_INSERT_ID();

INSERT INTO recipe_steps (recipe_id, step_number, action, instruction, duration, temperature, tools_used, tips)
VALUES
(@r, 1, '焯水去腥', '五花肉切大块冷水锅加料酒葱姜煮15分钟去血腥', 15, '大火', JSON_ARRAY('汤锅'), '块约4.5cm大小，冷冻半小时更好切'),
(@r, 2, '煎肉上色', '不放油直接中小火煎五花肉六面至出油', 5, '中小火', JSON_ARRAY('炒锅','锅铲'), '将煎出的油倒出备用'),
(@r, 3, '炒糖色', '锅中加15g冰糖翻炒融化，将五花肉与冰糖炒至融合上色', 3, '中小火', JSON_ARRAY('炒锅','锅铲'), '炒糖色注意不要炒焦'),
(@r, 4, '调味', '加入生抽10ml老抽15ml料酒5ml翻炒至上色', 2, '中火', JSON_ARRAY('炒锅'), '翻炒均匀让每块肉都上色'),
(@r, 5, '炖煮入味', '加开水没过食材放姜片香叶八角中小火炖煮40分钟，大火收汁加盐调味', 40, '中小火→大火', JSON_ARRAY('炒锅'), '中途翻搅防粘锅，收汁不可收干');
SET @s3_1 := LAST_INSERT_ID();

INSERT INTO step_tools (step_id, tool_id, `usage`) VALUES
(@s3_1, @t_stockpot, '焯水'),
(@s3_1+1, @t_wok, '煎制'), (@s3_1+1, @t_spatula, '翻面'),
(@s3_1+2, @t_wok, '炒糖'), (@s3_1+2, @t_spatula, '翻炒'),
(@s3_1+3, @t_wok, '翻炒'),
(@s3_1+4, @t_wok, '炖煮');

INSERT INTO recipe_ingredients (recipe_id, ingredient_id, quantity, unit, prep_method, prep_time, is_main, adjusted_calories, ingredient_type) VALUES
(@r, @i_pork,      '1500','g',  '切大块焯水', 15, 1, 5925.00, 'main'),
(@r, @i_rocksugar, '15', 'g',  '炒糖色',     0, 0,   59.55, 'seasoning'),
(@r, @i_soysauce,  '10', 'ml', '调味',       0, 0,    6.00, 'seasoning'),
(@r, @i_darksoy,   '15', 'ml', '上色',       0, 0,   10.80, 'seasoning'),
(@r, @i_shaoxing,  '5',  'ml', '去腥',       0, 0,    2.60, 'seasoning'),
(@r, @i_bayleaf,   '3',  '片', '炖煮',       0, 0,    9.39, 'seasoning'),
(@r, @i_staranise, '2',  '个', '炖煮',       0, 0,    6.74, 'seasoning'),
(@r, @i_salt,      '3',  'g',  '调味',       0, 0,    0.00, 'seasoning');

-- -----------------------------------------------
-- Recipe 4: 回锅肉 (★★★★ 川菜)
-- -----------------------------------------------
INSERT INTO recipes (name, description, total_time, servings, difficulty, cuisine_id, total_calories)
VALUES ('回锅肉', '经典川菜，五花肉搭配蒜苗豆瓣酱，酱香浓郁', 40, 2, 'hard', @c_sichuan, 680.00);
SET @r := LAST_INSERT_ID();

INSERT INTO recipe_steps (recipe_id, step_number, action, instruction, duration, temperature, tools_used, tips)
VALUES
(@r, 1, '处理五花肉', '锅烧热将五花肉皮紧压锅面炙皮，钢丝球刷净，冷水加姜片料酒葱煮至筷子可穿', 20, '大火', JSON_ARRAY('汤锅'), '要把碳化部分刷干净不然会苦'),
(@r, 2, '切片配菜', '五花肉过冷水晾凉切2mm薄片，青红椒切圈蒜苗切段姜切薄片', 8, '常温', JSON_ARRAY('砧板','菜刀'), '冷水晾凉后肉质更紧致好切'),
(@r, 3, '煸炒肉片', '锅烧热放底油放入五花肉煸炒至肥肉透明微卷', 3, '中火', JSON_ARRAY('炒锅','锅铲'), '煸炒至起灯盏窝效果最佳'),
(@r, 4, '调味翻炒', '倒入豆瓣酱生抽鸡精翻炒15秒，放青红椒姜片翻炒30秒，加蒜苗翻炒60秒出锅', 2, '大火', JSON_ARRAY('炒锅','锅铲'), '操作要迅速小心糊锅');
SET @s4_1 := LAST_INSERT_ID();

INSERT INTO step_tools (step_id, tool_id, `usage`) VALUES
(@s4_1, @t_stockpot, '焯煮'),
(@s4_1+1, @t_board, '切片'), (@s4_1+1, @t_knife, '切片'),
(@s4_1+2, @t_wok, '煸炒'), (@s4_1+2, @t_spatula, '翻炒'),
(@s4_1+3, @t_wok, '翻炒'), (@s4_1+3, @t_spatula, '翻炒');

INSERT INTO recipe_ingredients (recipe_id, ingredient_id, quantity, unit, prep_method, prep_time, is_main, adjusted_calories, ingredient_type) VALUES
(@r, @i_pork,       '250','g',  '煮熟切片',  20, 1, 987.50, 'main'),
(@r, @i_garlic_sprout,'1','把', '切段',       2, 0,  40.00, 'auxiliary'),
(@r, @i_pepper,     '30', 'g',  '切圈',      1, 0,   6.90, 'auxiliary'),
(@r, @i_douban,     '10', 'ml', '翻炒',      0, 0,  18.50, 'seasoning'),
(@r, @i_soysauce,   '5',  'ml', '调味',      0, 0,   3.00, 'seasoning'),
(@r, @i_shaoxing,   '5',  'ml', '焯水去腥',   0, 0,   2.60, 'seasoning'),
(@r, @i_msgsub,     '5',  'g',  '调味',      0, 0,  10.50, 'seasoning'),
(@r, @i_oil,        '10', 'ml', '底油',      0, 0,  88.40, 'seasoning');

-- -----------------------------------------------
-- Recipe 5: 糖醋排骨 (★★★★ 家常菜)
-- -----------------------------------------------
INSERT INTO recipes (name, description, total_time, servings, difficulty, cuisine_id, total_calories)
VALUES ('糖醋排骨', '传统名菜，独特酸甜口味，排骨酥嫩多汁', 45, 2, 'hard', @c_home, 520.00);
SET @r := LAST_INSERT_ID();

INSERT INTO recipe_steps (recipe_id, step_number, action, instruction, duration, temperature, tools_used, tips)
VALUES
(@r, 1, '焯水清洗', '排骨与姜片冷水下锅大火煮沸撇沫转小火焯水3分钟，开水清洗2-3遍', 10, '大火→小火', JSON_ARRAY('汤锅'), '焯水后用开水洗避免温差导致肉柴'),
(@r, 2, '深炸排骨', '锅中约300ml油加热至170°C下排骨炸3-5分钟至金黄捞出控油', 5, '170°C', JSON_ARRAY('炒锅'), '可轻撒干淀粉提升酥脆口感'),
(@r, 3, '熬糖水', '另起锅小火加50ml热水放30g白糖搅拌至完全溶解略呈淡黄色', 3, '小火', JSON_ARRAY('炒锅'), '重点是糖完全溶解不必过分依赖颜色'),
(@r, 4, '调味收汁', '排骨入糖水翻炒30秒加香醋生抽蚝油鸡精番茄酱五香粉再炒30秒，加开水没过排骨大火收汁，加老抽上色撒芝麻', 10, '大火', JSON_ARRAY('炒锅','锅铲'), '快速翻炒避免长时间煮炖损伤口感');
SET @s5_1 := LAST_INSERT_ID();

INSERT INTO step_tools (step_id, tool_id, `usage`) VALUES
(@s5_1, @t_stockpot, '焯水'),
(@s5_1+1, @t_wok, '炸制'),
(@s5_1+2, @t_wok, '熬糖'),
(@s5_1+3, @t_wok, '收汁'), (@s5_1+3, @t_spatula, '翻炒');

INSERT INTO recipe_ingredients (recipe_id, ingredient_id, quantity, unit, prep_method, prep_time, is_main, adjusted_calories, ingredient_type) VALUES
(@r, @i_ribs,      '300', 'g',  '焯水炸制',  10, 1, 792.00, 'main'),
(@r, @i_sugar,     '30',  'g',  '熬糖水',    0, 0, 116.10, 'seasoning'),
(@r, @i_oil,       '300', 'ml', '深炸',      0, 0, 2652.00,'seasoning'),
(@r, @i_vinegar,   '5',   'ml', '调味',      0, 0,    3.40, 'seasoning'),
(@r, @i_soysauce,  '5',   'ml', '调味',      0, 0,    3.00, 'seasoning'),
(@r, @i_oystersauce,'5',  'ml', '调味',      0, 0,    3.60, 'seasoning'),
(@r, @i_darksoy,   '5',   'ml', '上色',      0, 0,    3.60, 'seasoning'),
(@r, @i_ketchup,   '10',  'g',  '调味',      0, 0,    8.00, 'seasoning'),
(@r, @i_fivespice, '2',   'g',  '调味',      0, 0,    3.90, 'seasoning'),
(@r, @i_msgsub,    '2',   'g',  '调味',      0, 0,    4.20, 'seasoning'),
(@r, @i_sesame,    '2',   'g',  '装饰',      0, 0,   11.56, 'seasoning');

-- -----------------------------------------------
-- Recipe 6: 清蒸鲈鱼 (★★★ 粤菜)
-- -----------------------------------------------
INSERT INTO recipes (name, description, total_time, servings, difficulty, cuisine_id, total_calories)
VALUES ('清蒸鲈鱼', '粤式清蒸做法，鱼肉鲜嫩少油，保留海鲜原汁原味', 30, 2, 'medium', @c_cantonese, 360.00);
SET @r := LAST_INSERT_ID();

INSERT INTO recipe_steps (recipe_id, step_number, action, instruction, duration, temperature, tools_used, tips)
VALUES
(@r, 1, '处理腌制', '鲈鱼处理洗净擦干两面划刀用10g盐抹遍内外腌10分钟，鱼肚塞姜和葱白', 15, '常温', JSON_ARRAY('砧板','菜刀'), '刀花不要太深约到鱼骨即可'),
(@r, 2, '大火清蒸', '蒸锅水烧开后放入鱼用筷子垫起蒸盘大火蒸10分钟', 10, '大火', JSON_ARRAY('蒸锅'), '筷子垫起防止蒸出积水腥味，鱼眼凸起即熟'),
(@r, 3, '浇汁激香', '蒸好鱼去除姜蒜换干净盘，浇蒸鱼豉油撒姜葱丝，锅内烧热油淋至鱼身', 5, '大火', JSON_ARRAY('炒锅'), '热油激香是关键步骤');
SET @s6_1 := LAST_INSERT_ID();

INSERT INTO step_tools (step_id, tool_id, `usage`) VALUES
(@s6_1, @t_board, '清理'), (@s6_1, @t_knife, '改刀'),
(@s6_1+1, @t_steamer, '蒸制'),
(@s6_1+2, @t_wok, '烧油');

INSERT INTO recipe_ingredients (recipe_id, ingredient_id, quantity, unit, prep_method, prep_time, is_main, adjusted_calories, ingredient_type) VALUES
(@r, @i_bass,           '1',  '条', '处理划刀',   8, 1, 291.00, 'main'),
(@r, @i_scallion,       '3',  '根', '切段切丝',   3, 0,  15.00, 'auxiliary'),
(@r, @i_steamingsauce,  '15', 'ml', '浇汁',       0, 0,  10.80, 'seasoning'),
(@r, @i_shaoxing,       '15', 'ml', '腌制',       0, 0,   7.80, 'seasoning'),
(@r, @i_salt,           '10', 'g',  '腌制',       0, 0,   0.00, 'seasoning'),
(@r, @i_oil,            '15', 'ml', '热油激香',    0, 0, 132.60, 'seasoning');

-- -----------------------------------------------
-- Recipe 7: 白灼虾 (★★ 粤菜)
-- -----------------------------------------------
INSERT INTO recipes (name, description, total_time, servings, difficulty, cuisine_id, total_calories)
VALUES ('白灼虾', '非常适合沿海地区做，简单容错营养丰富，虾肉鲜甜', 20, 2, 'easy', @c_cantonese, 350.00);
SET @r := LAST_INSERT_ID();

INSERT INTO recipe_steps (recipe_id, step_number, action, instruction, duration, temperature, tools_used, tips)
VALUES
(@r, 1, '铺底蒸煮', '洋葱切小块姜切片平铺平底锅，活虾冲洗铺在上面倒入料酒盖盖中火1分钟小火5分钟关火5分钟', 11, '中火→小火', JSON_ARRAY('平底锅'), '开始不能大火防止糊底'),
(@r, 2, '制作蘸料', '葱切花蒜切碎倒入酱油芝麻香醋搅拌，油烧热淋入蘸料', 5, '大火', JSON_ARRAY('炒锅'), '蘸料可选纯醋更突出鲜味'),
(@r, 3, '出锅装盘', '虾出锅用干净盘子装好配蘸料', 1, '常温', JSON_ARRAY('平底锅'), NULL);
SET @s7_1 := LAST_INSERT_ID();

INSERT INTO step_tools (step_id, tool_id, `usage`) VALUES
(@s7_1, @t_flatpan, '蒸煮'),
(@s7_1+1, @t_wok, '烧油'),
(@s7_1+2, @t_flatpan, '出锅');

INSERT INTO recipe_ingredients (recipe_id, ingredient_id, quantity, unit, prep_method, prep_time, is_main, adjusted_calories, ingredient_type) VALUES
(@r, @i_shrimp,    '250', 'g',  '冲洗',      2, 1, 217.50, 'main'),
(@r, @i_onion,     '1',   '头', '切小块',    3, 0,  40.00, 'auxiliary'),
(@r, @i_shaoxing,  '20',  'ml', '蒸煮',      0, 0,  10.40, 'seasoning'),
(@r, @i_soy,       '15',  'ml', '蘸料',      0, 0,   9.00, 'seasoning'),
(@r, @i_sesame,    '5',   'g',  '蘸料',      0, 0,  28.90, 'seasoning'),
(@r, @i_vinegar,   '10',  'ml', '蘸料',      0, 0,   6.80, 'seasoning'),
(@r, @i_oystersauce,'10', 'ml', '蘸料',      0, 0,   7.20, 'seasoning'),
(@r, @i_oil,       '15',  'ml', '烧热淋入',   0, 0, 132.60, 'seasoning');

-- -----------------------------------------------
-- Recipe 8: 菠菜炒鸡蛋 (★★ 家常菜)
-- -----------------------------------------------
INSERT INTO recipes (name, description, total_time, servings, difficulty, cuisine_id, total_calories)
VALUES ('菠菜炒鸡蛋', '难度简单营养丰富的家常菜', 15, 1, 'easy', @c_home, 260.00);
SET @r := LAST_INSERT_ID();

INSERT INTO recipe_steps (recipe_id, step_number, action, instruction, duration, temperature, tools_used, tips)
VALUES
(@r, 1, '焯水备菜', '菠菜去根洗净焯水，鸡蛋打入碗中搅匀', 3, '大火', JSON_ARRAY('汤锅'), '焯水后沥干备用'),
(@r, 2, '煎蛋块', '热锅加10ml油，倒入蛋液中火翻炒15秒煎成蛋饼切小块盛出', 2, '中火', JSON_ARRAY('炒锅','锅铲'), '不要洗锅直接下一步'),
(@r, 3, '炒菠菜合炒', '再加5ml油油热放菠菜大火翻炒15秒倒入蛋块加盐和100ml水翻炒10秒', 1, '大火', JSON_ARRAY('炒锅','锅铲'), '大火快炒保持翠绿');
SET @s8_1 := LAST_INSERT_ID();

INSERT INTO step_tools (step_id, tool_id, `usage`) VALUES
(@s8_1, @t_stockpot, '焯水'),
(@s8_1+1, @t_wok, '煎蛋'), (@s8_1+1, @t_spatula, '翻炒'),
(@s8_1+2, @t_wok, '翻炒'), (@s8_1+2, @t_spatula, '翻炒');

INSERT INTO recipe_ingredients (recipe_id, ingredient_id, quantity, unit, prep_method, prep_time, is_main, adjusted_calories, ingredient_type) VALUES
(@r, @i_spinach, '350', 'g',  '焯水',   3, 1,  80.50, 'main'),
(@r, @i_egg,     '2',   '个', '打散',   1, 1, 143.00, 'main'),
(@r, @i_oil,     '15',  'ml', '炒制',   0, 0, 132.60, 'seasoning'),
(@r, @i_salt,    '5',   'g',  '调味',   0, 0,   0.00, 'seasoning');

-- -----------------------------------------------
-- Recipe 9: 蒜蓉西兰花 (★★ 家常菜)
-- -----------------------------------------------
INSERT INTO recipes (name, description, total_time, servings, difficulty, cuisine_id, total_calories)
VALUES ('蒜蓉西兰花', '爽脆西兰花配蒜蓉酱汁，清香提味低脂健康', 20, 2, 'easy', @c_home, 210.00);
SET @r := LAST_INSERT_ID();

INSERT INTO recipe_steps (recipe_id, step_number, action, instruction, duration, temperature, tools_used, tips)
VALUES
(@r, 1, '焯烫', '西兰花切小朵洗净沸水中大火煮2-3分钟至翠绿捞出沥干摆盘', 5, '大火', JSON_ARRAY('汤锅'), '焯水时间不宜过长保持脆度'),
(@r, 2, '炒蒜汁', '热锅加油小火煸蒜末出香味加生抽蚝油白糖和30ml水烧开', 3, '小火→大火', JSON_ARRAY('炒锅','锅铲'), '可加几滴香油提香'),
(@r, 3, '浇汁', '将蒜蓉汁均匀淋在盘中西兰花上', 1, '常温', NULL, NULL);
SET @s9_1 := LAST_INSERT_ID();

INSERT INTO step_tools (step_id, tool_id, `usage`) VALUES
(@s9_1, @t_stockpot, '焯烫'),
(@s9_1+1, @t_wok, '炒蒜汁'), (@s9_1+1, @t_spatula, '翻炒');

INSERT INTO recipe_ingredients (recipe_id, ingredient_id, quantity, unit, prep_method, prep_time, is_main, adjusted_calories, ingredient_type) VALUES
(@r, @i_broccoli,    '200', 'g',  '切小朵焯烫', 5, 1,  68.00, 'main'),
(@r, @i_soysauce,    '10',  'ml', '调汁',       0, 0,   6.00, 'seasoning'),
(@r, @i_oystersauce, '5',   'ml', '调汁',       0, 0,   3.60, 'seasoning'),
(@r, @i_sugar,       '2',   'g',  '调汁',       0, 0,   7.74, 'seasoning'),
(@r, @i_oil,         '10',  'ml', '炒蒜',       0, 0,  88.40, 'seasoning');

-- -----------------------------------------------
-- Recipe 10: 松仁玉米 (★★ 家常菜)
-- -----------------------------------------------
INSERT INTO recipes (name, description, total_time, servings, difficulty, cuisine_id, total_calories)
VALUES ('松仁玉米', '色香味俱全的家常菜，口感甜嫩松仁香脆老少皆宜', 15, 2, 'easy', @c_home, 350.00);
SET @r := LAST_INSERT_ID();

INSERT INTO recipe_steps (recipe_id, step_number, action, instruction, duration, temperature, tools_used, tips)
VALUES
(@r, 1, '焯水', '玉米粒和胡萝卜丁焯水1分钟捞出沥干', 3, '大火', JSON_ARRAY('汤锅'), '沥干水分避免炒制出水过多'),
(@r, 2, '翻炒', '热锅凉油放胡萝卜丁略炒加玉米粒翻炒，加白砂糖和盐炒匀', 3, '中火', JSON_ARRAY('炒锅','锅铲'), '火候不宜过大防糊锅'),
(@r, 3, '勾芡出锅', '水淀粉倒入快速翻炒汤汁略稠加松仁翻匀出锅', 2, '大火', JSON_ARRAY('炒锅','锅铲'), '松仁最后加入保持香脆');
SET @s10_1 := LAST_INSERT_ID();

INSERT INTO step_tools (step_id, tool_id, `usage`) VALUES
(@s10_1, @t_stockpot, '焯水'),
(@s10_1+1, @t_wok, '翻炒'), (@s10_1+1, @t_spatula, '翻炒'),
(@s10_1+2, @t_wok, '勾芡'), (@s10_1+2, @t_spatula, '翻炒');

INSERT INTO recipe_ingredients (recipe_id, ingredient_id, quantity, unit, prep_method, prep_time, is_main, adjusted_calories, ingredient_type) VALUES
(@r, @i_corn,      '200', 'g',  '焯水',       1, 1, 172.00, 'main'),
(@r, @i_pinenuts,  '30',  'g',  '备用',       0, 0, 201.90, 'auxiliary'),
(@r, @i_carrot,    '50',  'g',  '切丁焯水',    2, 0,  20.50, 'auxiliary'),
(@r, @i_sugar,     '10',  'g',  '调味',       0, 0,  38.70, 'seasoning'),
(@r, @i_salt,      '1',   'g',  '调味',       0, 0,   0.00, 'seasoning'),
(@r, @i_starch,    '5',   'g',  '勾芡',       0, 0,  19.05, 'seasoning'),
(@r, @i_oil,       '15',  'ml', '炒制',       0, 0, 132.60, 'seasoning');

-- -----------------------------------------------
-- Recipe 11: 西红柿鸡蛋汤 (★★ 汤粥)
-- -----------------------------------------------
INSERT INTO recipes (name, description, total_time, servings, difficulty, cuisine_id, total_calories)
VALUES ('西红柿鸡蛋汤', '简单易做营养丰富的家常汤品', 15, 2, 'easy', @c_soup, 180.00);
SET @r := LAST_INSERT_ID();

INSERT INTO recipe_steps (recipe_id, step_number, action, instruction, duration, temperature, tools_used, tips)
VALUES
(@r, 1, '备料', '西红柿洗净切块，葱姜蒜切碎，鸡蛋打入碗中搅匀', 5, '常温', JSON_ARRAY('砧板','菜刀'), NULL),
(@r, 2, '炒煮', '热锅放15ml油冒烟时放葱姜蒜翻炒30秒，放西红柿翻炒1分钟倒水1.2倍高度放盐', 5, '大火', JSON_ARRAY('汤锅','锅铲'), '油温冒烟时下料'),
(@r, 3, '蛋花收尾', '开锅后倒入蛋液用筷子打散放味素和香油等30秒关火', 2, '大火', JSON_ARRAY('汤锅'), '蛋液慢倒形成漂亮蛋花');
SET @s11_1 := LAST_INSERT_ID();

INSERT INTO step_tools (step_id, tool_id, `usage`) VALUES
(@s11_1, @t_board, '切块'), (@s11_1, @t_knife, '备料'),
(@s11_1+1, @t_stockpot, '炒煮'), (@s11_1+1, @t_spatula, '翻炒'),
(@s11_1+2, @t_stockpot, '煮汤');

INSERT INTO recipe_ingredients (recipe_id, ingredient_id, quantity, unit, prep_method, prep_time, is_main, adjusted_calories, ingredient_type) VALUES
(@r, @i_tomato,    '1',  '个', '切块',   2, 1,  18.00, 'main'),
(@r, @i_egg,       '2',  '个', '打散',   1, 1, 143.00, 'main'),
(@r, @i_sesameoil, '2',  '滴', '出锅加', 0, 0,   5.00, 'seasoning'),
(@r, @i_salt,      '15', 'g',  '调味',   0, 0,   0.00, 'seasoning'),
(@r, @i_oil,       '15', 'ml', '炒制',   0, 0, 132.60, 'seasoning');

-- -----------------------------------------------
-- Recipe 12: 蛋炒饭 (★★★ 主食)
-- -----------------------------------------------
INSERT INTO recipes (name, description, total_time, servings, difficulty, cuisine_id, total_calories)
VALUES ('蛋炒饭', '经典主食，使用隔夜冷饭炒出粒粒分明的口感', 20, 1, 'medium', @c_staple, 480.00);
SET @r := LAST_INSERT_ID();

INSERT INTO recipe_steps (recipe_id, step_number, action, instruction, duration, temperature, tools_used, tips)
VALUES
(@r, 1, '备料', '冷饭铲成小块，火腿黄瓜胡萝卜切丁，蛋白蛋黄分离搅匀', 5, '常温', JSON_ARRAY('砧板','菜刀'), '隔夜冷饭效果最佳，水分已流失'),
(@r, 2, '炒蛋', '大火热锅冒烟放油先炒蛋白凝固盛出，再炒蛋黄凝固后加配料翻炒10秒', 3, '大火', JSON_ARRAY('炒锅','锅铲'), '油温不可过高滑炒时间1分钟内'),
(@r, 3, '炒饭', '倒回蛋白翻炒5秒迅速倒入冷饭大火翻炒将块状捣碎使每粒饭裹上鸡蛋', 5, '大火', JSON_ARRAY('炒锅','锅铲'), '炒至米饭有跳起来的感觉即好'),
(@r, 4, '调味', '小火加盐胡椒粉生抽翻炒均匀最后加葱花翻炒10秒关火', 2, '小火', JSON_ARRAY('炒锅','锅铲'), '调味后不宜久炒');
SET @s12_1 := LAST_INSERT_ID();

INSERT INTO step_tools (step_id, tool_id, `usage`) VALUES
(@s12_1, @t_board, '切丁'), (@s12_1, @t_knife, '切丁'),
(@s12_1+1, @t_wok, '炒蛋'), (@s12_1+1, @t_spatula, '翻炒'),
(@s12_1+2, @t_wok, '炒饭'), (@s12_1+2, @t_spatula, '翻炒'),
(@s12_1+3, @t_wok, '调味'), (@s12_1+3, @t_spatula, '翻炒');

INSERT INTO recipe_ingredients (recipe_id, ingredient_id, quantity, unit, prep_method, prep_time, is_main, adjusted_calories, ingredient_type) VALUES
(@r, @i_rice,      '500', 'ml', '铲碎',       0, 1, 290.00, 'main'),
(@r, @i_egg,       '1',   '个', '分离打散',    1, 1,  71.50, 'main'),
(@r, @i_ham,       '2',   '根', '切丁',       1, 0, 106.00, 'auxiliary'),
(@r, @i_cucumber,  '30',  'g',  '切丁',       1, 0,   4.50, 'auxiliary'),
(@r, @i_carrot,    '30',  'g',  '切丁',       1, 0,  12.30, 'auxiliary'),
(@r, @i_oil,       '12',  'ml', '炒制',       0, 0, 106.08, 'seasoning'),
(@r, @i_salt,      '5',   'g',  '调味',       0, 0,   0.00, 'seasoning'),
(@r, @i_whitepep,  '8',   'g',  '调味',       0, 0,  20.40, 'seasoning'),
(@r, @i_soysauce,  '10',  'ml', '调味',       0, 0,   6.00, 'seasoning');

-- -----------------------------------------------
-- Recipe 13: 戚风蛋糕 (★★★★★ 甜品)
-- -----------------------------------------------
INSERT INTO recipes (name, description, total_time, servings, difficulty, cuisine_id, total_calories)
VALUES ('戚风蛋糕', '烘焙入门经典，口感细腻绵软。初学者需1.5-2小时完成', 120, 6, 'hard', @c_dessert, 800.00);
SET @r := LAST_INSERT_ID();

INSERT INTO recipe_steps (recipe_id, step_number, action, instruction, duration, temperature, tools_used, tips)
VALUES
(@r, 1, '分离蛋清蛋黄', '冰箱取出鸡蛋分离蛋清蛋黄至两个干净容器，蛋清容器不能有油蛋黄不能破', 5, '常温', JSON_ARRAY('搅拌碗'), '蛋清中不能混有任何蛋黄否则影响打发'),
(@r, 2, '搅拌蛋黄液', '食用油+面粉搅拌，加蛋黄牛奶和1/4糖，Z字形拌入低筋面粉至无干粉', 10, '常温', JSON_ARRAY('刮刀','搅拌碗'), '不可逆时针或顺时针搅拌避免起筋'),
(@r, 3, '打发蛋白', '蛋白分三次加糖用打蛋器打至干性发泡即直立尖角倒扣不掉', 15, '常温', JSON_ARRAY('打蛋器'), '打蛋器贴近容器底部防止上层打发底部液体'),
(@r, 4, '翻拌混合', '取1/3蛋白入蛋黄糊翻拌再全部倒回翻拌均匀避免消泡', 5, '常温', JSON_ARRAY('刮刀'), '翻拌手法避免画圈搅拌导致消泡'),
(@r, 5, '烘烤', '上150下160预热入下层烤制6寸30-35分钟', 35, '150-160°C', JSON_ARRAY('烤箱','模具'), '不能用不粘模具必须用铝合金阳极'),
(@r, 6, '冷却脱模', '出炉震出热气倒扣10分钟后脱模', 10, '常温', NULL, '必须倒扣否则回缩');
SET @s13_1 := LAST_INSERT_ID();

INSERT INTO step_tools (step_id, tool_id, `usage`) VALUES
(@s13_1+1, @t_scraper, '搅拌'),
(@s13_1+2, @t_whisk, '打发'),
(@s13_1+3, @t_scraper, '翻拌'),
(@s13_1+4, @t_oven, '烘烤'), (@s13_1+4, @t_mold, '成型');

INSERT INTO recipe_ingredients (recipe_id, ingredient_id, quantity, unit, prep_method, prep_time, is_main, adjusted_calories, ingredient_type) VALUES
(@r, @i_egg,      '3',  '个', '分离蛋清蛋黄', 5, 1, 214.50, 'main'),
(@r, @i_sugar,    '50', 'g',  '分次加入',     0, 0, 193.50, 'seasoning'),
(@r, @i_oil,      '25', 'g',  '拌入蛋黄液',   0, 0, 221.00, 'seasoning'),
(@r, @i_milk,     '30', 'ml', '拌入蛋黄液',   0, 0,  16.20, 'auxiliary'),
(@r, @i_lowflour, '50', 'g',  'Z字形拌入',    0, 1, 177.00, 'main');

-- -----------------------------------------------
-- Recipe 14: 煎饺 (★★ 早餐)
-- -----------------------------------------------
INSERT INTO recipes (name, description, total_time, servings, difficulty, cuisine_id, total_calories)
VALUES ('煎饺', '快手早餐，使用速冻饺子即可制作金黄酥脆的煎饺', 15, 1, 'easy', @c_breakfast, 430.00);
SET @r := LAST_INSERT_ID();

INSERT INTO recipe_steps (recipe_id, step_number, action, instruction, duration, temperature, tools_used, tips)
VALUES
(@r, 1, '煎制', '平底锅加10-15ml油放入饺子铺开加清水没过饺子1/2盖盖大火蒸8-10分钟', 10, '大火', JSON_ARRAY('平底锅'), '饺子不宜堆叠需平铺'),
(@r, 2, '煎至金黄', '水剩2mm时转中火煎至水分蒸发摇晃锅使受热均匀撒芝麻葱花焖10秒', 3, '中火', JSON_ARRAY('平底锅'), '观察底部出现金黄脆皮即可'),
(@r, 3, '出锅', '夹出观察底部金黄即可装盘', 1, '常温', JSON_ARRAY('平底锅'), '需时刻观察切记不可分神');
SET @s14_1 := LAST_INSERT_ID();

INSERT INTO step_tools (step_id, tool_id, `usage`) VALUES
(@s14_1, @t_flatpan, '煎制'),
(@s14_1+1, @t_flatpan, '煎制'),
(@s14_1+2, @t_flatpan, '出锅');

INSERT INTO recipe_ingredients (recipe_id, ingredient_id, quantity, unit, prep_method, prep_time, is_main, adjusted_calories, ingredient_type) VALUES
(@r, @i_dumpling, '15', '个', '直接使用', 0, 1, 322.50, 'main'),
(@r, @i_oil,      '15', 'ml','煎制',     0, 0, 132.60, 'seasoning'),
(@r, @i_sesame,   '5',  'g', '装饰',     0, 0,  28.90, 'seasoning');

-- -----------------------------------------------
-- Recipe 15: 酸梅汤 (★★★★ 饮品)
-- -----------------------------------------------
INSERT INTO recipes (name, description, total_time, servings, difficulty, cuisine_id, total_calories)
VALUES ('酸梅汤', '传统消暑饮品，酸甜适度滋味丰满悠长，冷藏后饮用更佳', 240, 4, 'hard', @c_drink, 450.00);
SET @r := LAST_INSERT_ID();

INSERT INTO recipe_steps (recipe_id, step_number, action, instruction, duration, temperature, tools_used, tips)
VALUES
(@r, 1, '浸泡', '冲洗乌梅乌枣山楂甘草陈皮（桂花冰糖除外）1.5L水常温浸泡2小时以上', 120, '常温', JSON_ARRAY('汤锅'), '充分浸泡有助于释放风味'),
(@r, 2, '头煎', '中大火煮沸盖盖转小火煮40分钟', 45, '小火', JSON_ARRAY('汤锅'), '保持微沸状态'),
(@r, 3, '融糖', '盆内放黄冰糖将沥好的头汤趁热倒入搅拌至冰糖融化', 5, '热', NULL, '趁热融化效果好'),
(@r, 4, '二煎', '药材重新装回锅加600ml水大火煮沸盖盖中火煮20分钟', 25, '中火', JSON_ARRAY('汤锅'), '二煎提取剩余风味'),
(@r, 5, '混合冷藏', '二煎与冰糖水趁热混合60-70°C加干桂花加盖晾凉冷藏3小时', 180, '60-70°C→冷藏', NULL, '桂花不超80°C否则失香');
SET @s15_1 := LAST_INSERT_ID();

INSERT INTO step_tools (step_id, tool_id, `usage`) VALUES
(@s15_1, @t_stockpot, '浸泡'),
(@s15_1+1, @t_stockpot, '煎煮'),
(@s15_1+3, @t_stockpot, '二煎');

INSERT INTO recipe_ingredients (recipe_id, ingredient_id, quantity, unit, prep_method, prep_time, is_main, adjusted_calories, ingredient_type) VALUES
(@r, @i_wumei,       '25',  'g', '冲洗浸泡', 120, 1,  73.00, 'main'),
(@r, @i_wuzao,       '25',  'g', '冲洗浸泡', 120, 0,  66.00, 'auxiliary'),
(@r, @i_hawthorn,    '30',  'g', '冲洗浸泡', 120, 0,  28.50, 'auxiliary'),
(@r, @i_y_rocksugar, '100', 'g', '融化',       0, 0, 397.00, 'seasoning'),
(@r, @i_licorice,    '2',   'g', '浸泡煎煮',   0, 0,   3.32, 'seasoning'),
(@r, @i_chenpi,      '4',   'g', '浸泡煎煮',   0, 0,   6.20, 'seasoning'),
(@r, @i_guihua,      '3',   'g', '60-70°C加入',0, 0,   8.64, 'seasoning');

COMMIT;
