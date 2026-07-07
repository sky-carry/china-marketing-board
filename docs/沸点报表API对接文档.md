# 沸点报表 API 对接文档

> 平台官方开放 API。本项目中 `pipeline/fetchers.py` 的 `fetch_fd_api` 即按本文档对接。
> 令牌由平台管理员发放；失效/更换请联系沸点平台管理员。

本文档提供**数据报表**与**订单报表**两个接口的 API 对接说明，供外部系统通过 API 令牌拉取数据。

---

## 一、通用说明

### 1. 基础信息

| 项目 | 说明 |
|---|---|
| 接口前缀（Base URL） | `https://api.fifay.cn/fifay-ad` |
| 请求方式 | POST |
| 内容类型 | `Content-Type: application/json` |
| 字符编码 | UTF-8 |

### 2. 鉴权

所有接口通过请求头携带 API 令牌鉴权：

```
Authorization: Bearer <你的令牌>
```

- 令牌无效 / 已停用 / 已过期，均返回登录错误码 **40001**。
- 请妥善保管令牌，避免泄露；如需更换请联系平台管理员。

### 3. 通用响应结构

```json
{
  "code": 200,
  "message": "success",
  "data": { }
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| code | int | 状态码，200 表示成功 |
| message | string | 提示信息 |
| data | object | 业务数据，见各接口说明 |

### 4. 分页结构

报表接口的 `data` 为分页对象：

| 字段 | 类型 | 说明 |
|---|---|---|
| list | array | 当前页数据列表 |
| total | long | 总条目数 |
| current | int | 当前页码 |
| endPage | boolean | 是否为最后一页 |

### 5. 通用错误码

| code | 说明 |
|---|---|
| 200 | 成功 |
| 20001 | 参数校验错误 |
| 20002 | 业务规则校验失败（如报表类型错误） |
| 30001 | 系统异常 |
| 40001 | 登录已过期（令牌无效 / 停用 / 过期） |

### 6. 数值单位与换算说明

为避免浮点精度问题，金额与比率均以整数返回，请按下述规则换算：

| 类型 | 单位 | 换算为常见单位 |
|---|---|---|
| 金额（字段注释含「分」，如 cost、orderAmount） | 分 | ÷ 100 = 元 |
| ROI（如 orderRoi） | 百分比 ×100 | ÷ 100 = 倍数（如 250 表示 2.5，即 250%） |
| 比率（如 ctr、orderRate） | 万分比 | ÷ 10000 = 比率（如 125 表示 1.25%） |

---

## 二、数据报表接口

获取按不同维度聚合的广告投放数据（曝光、点击、消耗、下单、ROI 等）。

### 1. 请求

```
POST https://api.fifay.cn/fifay-ad/report/union/get
Authorization: Bearer <你的令牌>
Content-Type: application/json
```

### 2. 请求参数（JSON Body）

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| adReportType | string | 是 | 报表维度类型，见下方「报表类型枚举」 |
| startDate | string | 是 | 开始日期，格式 yyyy-MM-dd（一个月内） |
| endDate | string | 是 | 结束日期，格式 yyyy-MM-dd |
| current | int | 否 | 页码，默认 1 |
| pageSize | int | 否 | 每页条数，默认 10 |
| advertiserName | string | 否 | 账户 ID 或账户名称过滤 |
| customizeFields | array | 否 | 自定义显示字段（**需要直接/间接数据，必须加上才会有**） |

> 说明：不同 adReportType 支持的过滤维度略有差异，未识别的参数会被忽略。

**报表类型枚举（adReportType）**

| code | 含义 |
|---|---|
| ADVERTISER | 账户维度 |
| PROJECT | 项目维度 |
| PROMOTION | 计划维度 |
| MATERIAL | 素材维度 |

### 3. 请求示例

```bash
curl -X POST 'https://api.fifay.cn/fifay-ad/report/union/get' \
  -H 'Authorization: Bearer sk-xxxx' \
  -H 'Content-Type: application/json' \
  -d '{
    "adReportType": "ADVERTISER",
    "startDate": "2026-07-01",
    "endDate": "2026-07-06",
    "current": 1,
    "pageSize": 20,
    "customizeFields": ["orderRoi", "cost"]
  }'
```

### 4. 响应字段（list / totalData 元素）

**基础指标**

| 字段 | 类型 | 单位 | 说明 |
|---|---|---|---|
| showCount | long | - | 曝光量 |
| clickCount | long | - | 点击量 |
| pageClickCount | long | - | 落地页点击量 |
| cost | long | 分 | 消耗 |
| convertCount | long | - | 转化数 |
| orderCount | long | - | 下单量 |
| orderAmount | long | 分 | 下单金额 |
| originOrderCount | long | - | 原始下单量 |
| originOrderAmount | long | 分 | 原始下单金额 |
| refundOrderCount | long | - | 退款下单量 |
| refundOrderAmount | long | 分 | 退款下单金额 |
| backOrderCount | long | - | 回流下单量 |
| backOrderAmount | long | 分 | 回流下单金额 |
| inAppOrderGmv | long | 分 | 引流电商订单 GMV |
| inAppOrderNetCount | long | - | 引流电商净成交订单数 |
| inAppOrderNetGmv | long | 分 | 引流电商净成交 GMV |
| totalPlay | long | - | 播放量 |
| validPlay | long | - | 有效播放数 |
| playDuration3s | long | - | 3 秒播放数 |
| playOver | long | - | 播放完成数 |
| dyLike | long | - | 点赞数 |
| dyComment | long | - | 评论量 |
| dyShare | long | - | 分享量 |

**衍生指标**

| 字段 | 类型 | 单位 | 说明 |
|---|---|---|---|
| ctr | long | 万分比 | 点击率（点击/曝光） |
| cpc | long | 分 | 点击成本（消耗/点击） |
| cpm | long | 分 | 千次曝光成本 |
| orderCost | long | 分 | 下单成本（消耗/下单量） |
| orderRate | long | 万分比 | 下单率（下单量/点击） |
| orderRoi | long | 百分比 | 下单 ROI（下单金额/消耗） |
| originOrderRoi | long | 百分比 | 原始下单 ROI |
| atv | long | 分 | 客单价（下单金额/下单量） |
| refundOrderRate | long | 万分比 | 订单退款率 |
| conversionCost | long | 分 | 平均转化成本 |
| conversionRate | long | 万分比 | 转化率 |
| collectCount | long | - | 收藏数 |
| cartCount | long | - | 加购数 |
| directOrderCount | long | - | 直接有效下单量 |
| directOrderAmount | long | 分 | 直接有效付款金额 |
| directOrderRoi | long | 百分比 | 直接有效付款 ROI |
| indirectOrderCount | long | - | 间接有效下单量 |
| indirectOrderAmount | long | 分 | 间接有效付款金额 |
| indirectOrderRoi | long | 百分比 | 间接有效付款 ROI |

> 除以上指标外，响应元素还会包含对应维度的标识字段（如账户 ID/名称、计划 ID/名称、日期等），具体随 adReportType 变化。
>
> 实测（本项目验证）：`customizeFields` 传全字段时，还会返回 `directOriginOrderCount/Amount/Roi`（直接原始）等；不传时 direct* 字段值为 0。

### 5. 响应示例

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "list": [
      {
        "showCount": 120000,
        "clickCount": 3600,
        "cost": 158000,
        "orderCount": 42,
        "orderAmount": 396000,
        "orderRoi": 250,
        "ctr": 300
      }
    ],
    "totalData": {
      "showCount": 120000, "clickCount": 3600, "cost": 158000,
      "orderCount": 42, "orderAmount": 396000
    },
    "total": 1, "current": 1, "endPage": true
  }
}
```

---

## 三、订单报表接口

获取订单明细数据（下单时间、商品、金额、归因、订单状态等）。**当前项目尚未接入，后续做订单级归因分析可用。**

### 1. 请求

```
POST https://api.fifay.cn/fifay-ad/report/order/get
Authorization: Bearer <你的令牌>
Content-Type: application/json
```

### 2. 请求参数（JSON Body）

订单报表固定为订单明细维度，`adReportType` 无需传递。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| startDate | string | 是 | 开始日期，格式 yyyy-MM-dd |
| endDate | string | 是 | 结束日期，格式 yyyy-MM-dd |
| current | int | 否 | 页码，默认 1 |
| pageSize | int | 否 | 每页条数，默认 10 |
| advertiserName | string | 否 | 账户 ID 或账户名称过滤 |
| adId | long | 否 | 计划 ID 过滤 |
| orderNo | string | 否 | 订单编号过滤 |
| goodsId | string | 否 | 商品 ID 过滤 |
| convertStatus | int | 否 | 回传状态：1=已回传，0=未回传 |

### 3. 响应字段（list 元素）

| 字段 | 类型 | 单位 | 说明 |
|---|---|---|---|
| id | long | - | 记录 ID |
| orderParentNo | string | - | 订单编号 |
| orderNo | string | - | 订单子编号 |
| orderCreateTime | datetime | - | 创建时间 |
| orderClickTime | datetime | - | 点击时间 |
| orderPayTime | datetime | - | 下单（付款）时间 |
| orderRefundTime | datetime | - | 退款时间 |
| goodsId | string | - | 商品 ID |
| goodsInfo | string | - | 商品名称 |
| goodsNum | int | - | 商品数量 |
| goodsPrice | long | 元 | 商品价格 |
| goodsPic | string | - | 商品图片 |
| payMoney | long | 元 | 支付金额 |
| adId | string | - | 计划 ID |
| adName | string | - | 计划名称 |
| advertiserId | string | - | 账户 ID |
| advertiserName | string | - | 账户名称 |
| remark | string | - | 账户备注 |
| sellerStore | string | - | 店铺名称 |
| orderStatus | string | - | 订单状态 |
| convertStatus | string | - | 回传状态 |
| channelSite | string | - | 广告版位 |
| orderSource | string | - | 订单来源 |
| orderDisplaySource | string | - | 订单来源（展示用） |
| materialId | string | - | 素材 ID |
| promotionStatus | int | - | 推广状态 |
| tracePoint | int | - | 归因触点：1=曝光，2=有效播放+点击，3=联盟点击 |
| traceScope | int | - | 归因结果：2=同店，4=同 SPU |

---

## 四、对接注意事项

1. 两个接口均为 POST + JSON，务必设置 `Content-Type: application/json`。
2. 令牌通过 `Authorization: Bearer <令牌>` 传递，缺失或错误返回 **40001**。
3. 金额、比率为整数编码，请按「数值单位与换算说明」换算后再展示。
4. 大批量拉取建议按日期范围分页循环获取，避免单次请求数据量过大。
5. 返回 `code != 200` 时，请读取 message 获取失败原因并做好重试/告警。
