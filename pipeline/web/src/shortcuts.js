// 统一的日期范围快捷选项（所有日期选择框共用，改这里即全站生效）
// 周以「周一」为一周起始（国内习惯）。配合 el-date-picker value-format="YYYY-MM-DD" 使用。
const D = 864e5
const lastN = n => [new Date(Date.now() - (n - 1) * D), new Date()]   // 近N天(含今天)

export const dateShortcuts = [
  { text: '今天',   value: () => { const d = new Date(); return [d, d] } },
  { text: '昨天',   value: () => { const d = new Date(Date.now() - D); return [d, d] } },
  { text: '近7天',  value: () => lastN(7) },
  { text: '近15天', value: () => lastN(15) },
  { text: '近30天', value: () => lastN(30) },
  { text: '近90天', value: () => lastN(90) },
  { text: '本周',   value: () => { const d = new Date(); const w = (d.getDay() + 6) % 7; const s = new Date(d); s.setDate(d.getDate() - w); return [s, new Date()] } },
  { text: '上周',   value: () => { const d = new Date(); const w = (d.getDay() + 6) % 7; const mon = new Date(d); mon.setDate(d.getDate() - w); const s = new Date(mon); s.setDate(mon.getDate() - 7); const e = new Date(mon); e.setDate(mon.getDate() - 1); return [s, e] } },
  { text: '本月',   value: () => { const n = new Date(); return [new Date(n.getFullYear(), n.getMonth(), 1), n] } },
  { text: '上月',   value: () => { const n = new Date(); return [new Date(n.getFullYear(), n.getMonth() - 1, 1), new Date(n.getFullYear(), n.getMonth(), 0)] } },
  { text: '本季度', value: () => { const n = new Date(); const q = Math.floor(n.getMonth() / 3); return [new Date(n.getFullYear(), q * 3, 1), n] } },
  { text: '上季度', value: () => { const n = new Date(); const q = Math.floor(n.getMonth() / 3); let y = n.getFullYear(), m = (q - 1) * 3; if (m < 0) { y--; m = 9 } return [new Date(y, m, 1), new Date(y, m + 3, 0)] } },
]

export default dateShortcuts
