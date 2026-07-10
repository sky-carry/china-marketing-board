<template>
  <div class="card grow">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;gap:12px;flex-wrap:wrap">
      <span style="color:#909399;font-size:13px">
        共 {{ rows.length }} 个投放账户（<b style="color:#e6a23c">{{ incompleteCount }} 待填</b> / {{ completeCount }} 完整，<b>未填的排在最前</b>）。
        六个属性都填才算完整；填完可在「账户看板」的<b>自定义列</b>勾选展示。可导出 Excel 给同事离线填、再导回。
      </span>
      <div style="display:flex;gap:8px;align-items:center">
        <el-input v-model="search" size="small" style="width:190px" clearable placeholder="搜索账户名/ID，回车"
          @keyup.enter="load" @clear="load" />
        <el-button size="small" @click="exportXlsx" :loading="exporting">
          <el-icon style="margin-right:4px"><Download /></el-icon>导出Excel
        </el-button>
        <el-button size="small" type="primary" @click="pickFile" :loading="importing">
          <el-icon style="margin-right:4px"><Upload /></el-icon>导入Excel
        </el-button>
        <input ref="fileInput" type="file" accept=".xlsx" style="display:none" @change="onFile" />
      </div>
    </div>
    <div class="table-wrap">
      <el-table :data="rows" size="small" border v-loading="loading" height="100%">
        <el-table-column label="状态" width="78" fixed="left">
          <template #default="{ row }">
            <el-tag v-if="row.complete" type="success" size="small" effect="plain">完整</el-tag>
            <el-tag v-else type="warning" size="small" effect="plain">{{ row.filled ? ('缺'+(6-row.filled)+'项') : '未填' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="账户名称" prop="entity_name" min-width="220" show-overflow-tooltip fixed="left" />
        <el-table-column label="账户ID" prop="entity_id" width="155" />
        <el-table-column label="平台" width="84">
          <template #default="{ row }">
            <el-tag v-for="p in row.platforms" :key="p" size="small" effect="plain" style="margin:1px">{{ p }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column v-for="f in fields" :key="f.key" :label="f.label" min-width="128">
          <template #default="{ row }">
            <el-select v-model="row[f.key]" size="small" filterable allow-create clearable default-first-option
              placeholder="—" style="width:100%" @change="v => save(row, f.key, v)">
              <el-option v-for="o in (options[f.key] || [])" :key="o" :label="o" :value="o" />
            </el-select>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api'
import { ElMessage } from 'element-plus'
import { Download, Upload } from '@element-plus/icons-vue'

const rows = ref([]); const fields = ref([]); const options = ref({})
const loading = ref(false); const search = ref('')
const exporting = ref(false); const importing = ref(false); const fileInput = ref(null)

const completeCount = computed(() => rows.value.filter(r => r.complete).length)
const incompleteCount = computed(() => rows.value.length - completeCount.value)

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/adv_accounts', { params: { search: search.value || undefined } })
    rows.value = data.rows; fields.value = data.fields; options.value = data.options || {}
  } finally { loading.value = false }
}
async function save(row, key, val) {
  try {
    await api.post('/account_meta', { entity_id: row.entity_id, [key]: val || '' })
    row.filled = fields.value.reduce((n, f) => n + (row[f.key] ? 1 : 0), 0)
    row.complete = row.filled === fields.value.length
    if (val && !(options.value[key] || []).includes(val)) options.value[key] = [...(options.value[key] || []), val].sort()
  } catch (e) { ElMessage.error('保存失败：' + (e?.response?.data?.detail || e.message)) }
}
async function exportXlsx() {
  exporting.value = true
  try {
    const res = await api.get('/adv_accounts/export', { responseType: 'blob' })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a'); a.href = url; a.download = '投放账户属性表.xlsx'; a.click()
    URL.revokeObjectURL(url)
  } catch (e) { ElMessage.error('导出失败：' + (e?.message || e)) } finally { exporting.value = false }
}
function pickFile() { fileInput.value.click() }
async function onFile(e) {
  const f = e.target.files[0]; e.target.value = ''
  if (!f) return
  importing.value = true
  try {
    const { data } = await api.post('/adv_accounts/import', f, { headers: { 'Content-Type': 'application/octet-stream' } })
    ElMessage.success(`导入成功，更新 ${data.updated} 个账户`); load()
  } catch (err) { ElMessage.error('导入失败：' + (err?.response?.data?.detail || err.message)) } finally { importing.value = false }
}
onMounted(load)
</script>
