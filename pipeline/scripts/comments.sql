-- 为 ad_data 库所有表 / 字段补充中文注释（可重复执行）
-- 运行：psql "postgresql://postgres:postgres@localhost:5432/ad_data" -f comments.sql

-- ============================ accounts 各平台登录账号（凭证）注册表 ============================
COMMENT ON TABLE  accounts                  IS '各平台登录账号（凭证）注册表';
COMMENT ON COLUMN accounts.id               IS '主键';
COMMENT ON COLUMN accounts.platform         IS '平台名（小飞机/沸点/微橙/麦斯/博擎/方块）';
COMMENT ON COLUMN accounts.tag              IS '账号标识（唯一），对应 ad_daily.login_account';
COMMENT ON COLUMN accounts.auth             IS '认证信息 JSON（token/cookie/session/x_token/api_key 等）';
COMMENT ON COLUMN accounts.enabled          IS '是否启用（参与抓取）';
COMMENT ON COLUMN accounts.token_status     IS '令牌状态（ok=有效 / expired=过期 / need_login=需人工登录 / unknown=未知）';
COMMENT ON COLUMN accounts.token_updated_at IS '令牌最近更新时间';
COMMENT ON COLUMN accounts.note             IS '备注';
COMMENT ON COLUMN accounts.created_at       IS '创建时间';
COMMENT ON COLUMN accounts.username         IS '平台登录用户名/邮箱（供密码自动登录）';
COMMENT ON COLUMN accounts.password         IS '平台登录密码（供密码自动登录；小飞机需验证码除外）';
COMMENT ON COLUMN accounts.is_historical    IS '是否历史账号（停投）：true=不参与定时抓取、列表置底，数据保留';

-- ============================ ad_daily 广告投放按日明细（各平台归一化统一指标） ============================
COMMENT ON TABLE  ad_daily                  IS '广告投放按日明细（各平台归一化后的统一指标表）';
COMMENT ON COLUMN ad_daily.platform         IS '平台名（小飞机/沸点/微橙/麦斯/博擎/方块）';
COMMENT ON COLUMN ad_daily.login_account    IS '登录账号标识（对应 accounts.tag）';
COMMENT ON COLUMN ad_daily.level            IS '维度层级（账户/广告组/广告/计划/单元/创意/素材 等）';
COMMENT ON COLUMN ad_daily.date             IS '数据日期（北京时间）';
COMMENT ON COLUMN ad_daily.entity_id        IS '实体ID（当前层级对象ID）';
COMMENT ON COLUMN ad_daily.entity_name      IS '实体名称';
COMMENT ON COLUMN ad_daily.account_id       IS '账户ID';
COMMENT ON COLUMN ad_daily.account_name     IS '账户名称';
COMMENT ON COLUMN ad_daily.parent_id        IS '上级实体ID';
COMMENT ON COLUMN ad_daily.parent_name      IS '上级实体名称';
COMMENT ON COLUMN ad_daily.channel          IS '投放渠道/媒体（如 巨量引擎 / 小红书聚光 / 巨量千川）';
COMMENT ON COLUMN ad_daily.cost             IS '消耗（元）';
COMMENT ON COLUMN ad_daily.impressions      IS '展示量';
COMMENT ON COLUMN ad_daily.clicks           IS '点击量';
COMMENT ON COLUMN ad_daily.ctr              IS '点击率（%）';
COMMENT ON COLUMN ad_daily.cpm              IS '千次展示成本（元）';
COMMENT ON COLUMN ad_daily.cpc              IS '平均点击单价（元）';
COMMENT ON COLUMN ad_daily.conversions      IS '转化数';
COMMENT ON COLUMN ad_daily.conversion_cost  IS '转化成本（元）';
COMMENT ON COLUMN ad_daily.orders           IS '下单量';
COMMENT ON COLUMN ad_daily.pay_amount       IS '下单金额（元）';
COMMENT ON COLUMN ad_daily.roi              IS '下单ROI';
COMMENT ON COLUMN ad_daily.real_pay_amount  IS '真实成交金额（元）';
COMMENT ON COLUMN ad_daily.real_orders      IS '真实成交订单数';
COMMENT ON COLUMN ad_daily.real_roi         IS '真实成交ROI';
COMMENT ON COLUMN ad_daily.refund_rate      IS '退款率（%）';
-- 直投归因指标（小飞机=直推 / 沸点=直接 / 微橙=单品 / 麦斯=主投品 / 方块=直接）：下单(gross) 与 成交(net) 两组
COMMENT ON COLUMN ad_daily.direct_orders          IS '直投下单量（直推付款订单数/直接原始订单量/单品订单数/主投品下单量）';
COMMENT ON COLUMN ad_daily.direct_pay_amount      IS '直投下单金额（元）';
COMMENT ON COLUMN ad_daily.direct_roi             IS '直投下单ROI';
COMMENT ON COLUMN ad_daily.direct_real_orders     IS '直投成交量（真实直推付款订单数/直接有效下单量/单品下单订单数/主投品成交量）';
COMMENT ON COLUMN ad_daily.direct_real_pay_amount IS '直投成交金额（元）';
COMMENT ON COLUMN ad_daily.direct_real_roi        IS '直投成交ROI';
COMMENT ON COLUMN ad_daily.fetched_at       IS '抓取入库时间';

-- ============================ crawl_progress 抓取进度（幂等去重） ============================
COMMENT ON TABLE  crawl_progress               IS '抓取进度记录（已抓过的 平台+账号+层级+日期 组合可跳过，用于幂等去重）';
COMMENT ON COLUMN crawl_progress.platform      IS '平台名';
COMMENT ON COLUMN crawl_progress.login_account IS '登录账号标识（对应 accounts.tag）';
COMMENT ON COLUMN crawl_progress.level         IS '维度层级';
COMMENT ON COLUMN crawl_progress.date          IS '数据日期';
COMMENT ON COLUMN crawl_progress.rows          IS '该组合抓取到的行数';
COMMENT ON COLUMN crawl_progress.fetched_at    IS '抓取时间';

-- ============================ tasks 定时抓取任务配置 ============================
COMMENT ON TABLE  tasks                  IS '定时抓取任务配置';
COMMENT ON COLUMN tasks.id               IS '主键';
COMMENT ON COLUMN tasks.name             IS '任务名称';
COMMENT ON COLUMN tasks.kind             IS '任务类型（rolling=滚动近N天 / backfill=历史回补）';
COMMENT ON COLUMN tasks.platform         IS '限定平台（NULL=全部平台）';
COMMENT ON COLUMN tasks.window_days      IS '滚动窗口天数（抓取近N天）';
COMMENT ON COLUMN tasks.interval_minutes IS '运行间隔（分钟）';
COMMENT ON COLUMN tasks.enabled          IS '是否启用';
COMMENT ON COLUMN tasks.last_run_at      IS '上次运行时间';
COMMENT ON COLUMN tasks.last_status      IS '上次运行状态';
COMMENT ON COLUMN tasks.created_at       IS '创建时间';
COMMENT ON COLUMN tasks.daily_time       IS '每日定时时间(HH:MM)，为空则按 interval_minutes 间隔跑';

-- ============================ runs 任务运行记录 ============================
COMMENT ON TABLE  runs               IS '任务运行记录（每次执行一条）';
COMMENT ON COLUMN runs.id            IS '主键';
COMMENT ON COLUMN runs.task_id       IS '关联任务ID（tasks.id）';
COMMENT ON COLUMN runs.kind          IS '任务类型（rolling/backfill）';
COMMENT ON COLUMN runs.started_at    IS '开始时间';
COMMENT ON COLUMN runs.finished_at   IS '结束时间';
COMMENT ON COLUMN runs.status        IS '运行状态（running=进行中 / ok=成功 / error=失败）';
COMMENT ON COLUMN runs.rows_written  IS '写入行数';
COMMENT ON COLUMN runs.detail        IS '详情/错误信息';

-- ============================ account_tags 投放账户标签 ============================
COMMENT ON TABLE  account_tags            IS '投放账户标签（人工打标，按 平台+账户ID）';
COMMENT ON COLUMN account_tags.platform   IS '平台名';
COMMENT ON COLUMN account_tags.entity_id  IS '账户ID（账户级 entity_id，即巨量广告主ID）';
COMMENT ON COLUMN account_tags.tags       IS '标签数组（JSON）';
COMMENT ON COLUMN account_tags.updated_at IS '更新时间';

-- ============================ account_meta 投放账户自定义属性 ============================
COMMENT ON TABLE  account_meta               IS '投放账户自定义属性（按账户ID存，跨平台共享；供账户看板自定义列、投放账户管理页编辑）';
COMMENT ON COLUMN account_meta.entity_id     IS '账户ID（账户级 entity_id，即巨量广告主ID）';
COMMENT ON COLUMN account_meta.category      IS '类目';
COMMENT ON COLUMN account_meta.product       IS '投放产品';
COMMENT ON COLUMN account_meta.ecom_platform IS '电商平台（京东/天猫等）';
COMMENT ON COLUMN account_meta.ad_channel    IS '投放渠道（抖音JDS/抖音CID/小红书CID等）';
COMMENT ON COLUMN account_meta.store         IS '店铺（自营/旗舰/官旗等）';
COMMENT ON COLUMN account_meta.agency        IS '代理商';
COMMENT ON COLUMN account_meta.updated_at    IS '更新时间';

-- ============================ auth_users 看板登录用户 ============================
COMMENT ON TABLE  auth_users            IS '看板登录用户（本系统自身的登录鉴权，非投放平台账号）';
COMMENT ON COLUMN auth_users.username   IS '登录用户名';
COMMENT ON COLUMN auth_users.salt       IS '密码盐值（hex）';
COMMENT ON COLUMN auth_users.pw_hash    IS '密码哈希（pbkdf2-sha256）';
COMMENT ON COLUMN auth_users.updated_at IS '更新时间';

-- ============================ orders 订单明细（沸点订单报表） ============================
COMMENT ON TABLE  orders                  IS '订单明细（来自沸点订单报表 report/order/get），一订单一行';
COMMENT ON COLUMN orders.platform         IS '平台名（沸点等）';
COMMENT ON COLUMN orders.login_account    IS '登录账号标识（对应 accounts.tag）';
COMMENT ON COLUMN orders.order_type       IS '订单类型（如 电商订单）';
COMMENT ON COLUMN orders.order_date       IS '订单日期（统计日）';
COMMENT ON COLUMN orders.ad_account_name  IS '广告账户名称';
COMMENT ON COLUMN orders.ad_account_id    IS '广告账户ID（巨量广告主ID）';
COMMENT ON COLUMN orders.ad_name          IS '计划/广告名称';
COMMENT ON COLUMN orders.material_name    IS '素材名称/素材ID';
COMMENT ON COLUMN orders.main_order_no    IS '主订单编号';
COMMENT ON COLUMN orders.order_no         IS '子订单编号';
COMMENT ON COLUMN orders.product_info     IS '商品名称';
COMMENT ON COLUMN orders.product_price    IS '商品价格（元）';
COMMENT ON COLUMN orders.pay_amount       IS '支付金额（元）';
COMMENT ON COLUMN orders.order_status     IS '订单状态（已付款/退款等）';
COMMENT ON COLUMN orders.callback_status  IS '回传状态（是否已回传媒体：1=已回传/0=未回传）';
COMMENT ON COLUMN orders.click_time       IS '点击时间';
COMMENT ON COLUMN orders.pay_time         IS '付款时间';
COMMENT ON COLUMN orders.refund_time      IS '退款时间';
COMMENT ON COLUMN orders.attribution      IS '归因（触点/结果口径）';
COMMENT ON COLUMN orders.ad_position      IS '广告版位（抖音等）';
COMMENT ON COLUMN orders.category         IS '类目（来自投放账户属性 account_meta）';
COMMENT ON COLUMN orders.product          IS '投放产品（来自投放账户属性）';
COMMENT ON COLUMN orders.ecom_platform    IS '电商平台（来自投放账户属性）';
COMMENT ON COLUMN orders.channel          IS '投放渠道（来自投放账户属性）';
COMMENT ON COLUMN orders.shop             IS '店铺（来自投放账户属性）';
COMMENT ON COLUMN orders.agency           IS '代理商（来自投放账户属性）';
COMMENT ON COLUMN orders.fetched_at       IS '抓取入库时间';

-- 用户表（飞书登录用户，开放注册，首次登录自动建号；与共享密码账户 auth_users 独立）
COMMENT ON TABLE  users                IS '飞书登录用户（开放注册，首次登录自动建号）';
COMMENT ON COLUMN users.open_id        IS '飞书用户唯一ID（应用内），登录按此 UPSERT';
COMMENT ON COLUMN users.union_id       IS '飞书跨应用唯一ID';
COMMENT ON COLUMN users.feishu_user_id IS '租户内 user_id';
COMMENT ON COLUMN users.name           IS '显示名（飞书姓名）';
COMMENT ON COLUMN users.avatar_url     IS '头像URL';
COMMENT ON COLUMN users.email          IS '邮箱（需飞书授权对应权限，可能为空）';
COMMENT ON COLUMN users.mobile         IS '手机号（需飞书授权对应权限，可能为空）';
COMMENT ON COLUMN users.source         IS '来源：feishu/password/dev';
COMMENT ON COLUMN users.is_active      IS '是否允许登录（禁用某人置 false）';
COMMENT ON COLUMN users.is_admin       IS '管理员标记（预留，供以后分权限用）';
COMMENT ON COLUMN users.first_login_at IS '首次登录时间';
COMMENT ON COLUMN users.last_login_at  IS '最近登录时间';
COMMENT ON COLUMN users.login_count    IS '累计登录次数';
COMMENT ON COLUMN users.created_at     IS '创建时间';
COMMENT ON COLUMN users.updated_at     IS '更新时间';
