-- 为 ad_data 库所有表 / 字段补充中文注释（可重复执行）
-- 运行：psql "postgresql://postgres:postgres@localhost:5432/ad_data" -f comments.sql

-- ============================ accounts 各平台登录账号（凭证）注册表 ============================
COMMENT ON TABLE  accounts                  IS '各平台登录账号（凭证）注册表';
COMMENT ON COLUMN accounts.id               IS '主键';
COMMENT ON COLUMN accounts.platform         IS '平台名（小飞机/沸点/微橙/麦斯）';
COMMENT ON COLUMN accounts.tag              IS '账号标识（唯一），对应 ad_daily.login_account';
COMMENT ON COLUMN accounts.auth             IS '认证信息 JSON（token/cookie/session/x_token 等）';
COMMENT ON COLUMN accounts.enabled          IS '是否启用（参与抓取）';
COMMENT ON COLUMN accounts.token_status     IS '令牌状态（ok=有效 / expired=过期 / unknown=未知）';
COMMENT ON COLUMN accounts.token_updated_at IS '令牌最近更新时间';
COMMENT ON COLUMN accounts.note             IS '备注';
COMMENT ON COLUMN accounts.created_at       IS '创建时间';

-- ============================ ad_daily 广告投放按日明细（各平台归一化统一指标） ============================
COMMENT ON TABLE  ad_daily                  IS '广告投放按日明细（各平台归一化后的统一指标表）';
COMMENT ON COLUMN ad_daily.platform         IS '平台名（小飞机/沸点/微橙/麦斯）';
COMMENT ON COLUMN ad_daily.login_account    IS '登录账号标识（对应 accounts.tag）';
COMMENT ON COLUMN ad_daily.level            IS '维度层级（账户/广告组/广告/计划/单元/创意/素材 等）';
COMMENT ON COLUMN ad_daily.date             IS '数据日期（北京时间）';
COMMENT ON COLUMN ad_daily.entity_id        IS '实体ID（当前层级对象ID）';
COMMENT ON COLUMN ad_daily.entity_name      IS '实体名称';
COMMENT ON COLUMN ad_daily.account_id       IS '账户ID';
COMMENT ON COLUMN ad_daily.account_name     IS '账户名称';
COMMENT ON COLUMN ad_daily.parent_id        IS '上级实体ID';
COMMENT ON COLUMN ad_daily.parent_name      IS '上级实体名称';
COMMENT ON COLUMN ad_daily.channel          IS '投放渠道/媒体（如 巨量引擎 / 小红书聚光 / 沸点）';
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
