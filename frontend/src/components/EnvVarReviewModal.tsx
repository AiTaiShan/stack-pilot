import React, { useEffect, useState } from 'react'
import {
  Modal, Table, Button, Input, Space, message, Tooltip,
  Popconfirm, Typography, Alert, Empty,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined,
  CheckCircleOutlined, WarningOutlined,
} from '@ant-design/icons'
import client from '../api/client'

const { Text } = Typography

interface EnvVarRecord {
  key: string
  value: string
}

interface Props {
  deploymentId: string
  open: boolean
  onClose: () => void
  onConfirmed: () => void
}

const EnvVarReviewModal: React.FC<Props> = ({
  deploymentId, open, onClose, onConfirmed,
}) => {
  const [envVars, setEnvVars] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [newKey, setNewKey] = useState('')
  const [newValue, setNewValue] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [editVal, setEditVal] = useState('')

  const fetchVars = async () => {
    setLoading(true)
    try {
      const res = await client.get(`/deployments/${deploymentId}/env-vars`)
      setEnvVars(res.data.data?.pending_env_vars || {})
    } catch (err: any) {
      message.error(err.response?.data?.detail || '获取环境变量失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (open) fetchVars()
  }, [open, deploymentId])

  const handleAdd = async () => {
    if (!newKey.trim() || !newValue.trim()) {
      message.warning('请填写变量名和变量值')
      return
    }
    try {
      await client.put(`/deployments/${deploymentId}/env-vars`, {
        [newKey.trim()]: newValue.trim(),
      })
      setEnvVars(p => ({ ...p, [newKey.trim()]: newValue.trim() }))
      setNewKey(''); setNewValue(''); setShowAdd(false)
      message.success('已添加')
    } catch (err: any) {
      message.error(err.response?.data?.detail || '添加失败')
    }
  }

  const handleDelete = async (key: string) => {
    try {
      await client.delete(`/deployments/${deploymentId}/env-vars`, {
        data: { keys: [key] },
      })
      setEnvVars(p => { const n = { ...p }; delete n[key]; return n })
      message.success(`已删除 ${key}`)
    } catch (err: any) {
      message.error(err.response?.data?.detail || '删除失败')
    }
  }

  const handleSaveEdit = async (key: string) => {
    if (!editVal.trim()) { message.warning('请输入变量值'); return }
    try {
      await client.put(`/deployments/${deploymentId}/env-vars`, {
        [key]: editVal.trim(),
      })
      setEnvVars(p => ({ ...p, [key]: editVal.trim() }))
      setEditingKey(null)
      message.success('已更新')
    } catch (err: any) {
      message.error(err.response?.data?.detail || '更新失败')
    }
  }

  const handleConfirm = async () => {
    setConfirming(true)
    try {
      await client.post(`/deployments/${deploymentId}/confirm-env-vars`)
      message.success('环境变量已确认，部署继续')
      onConfirmed()
    } catch (err: any) {
      message.error(err.response?.data?.detail || '确认失败')
    } finally {
      setConfirming(false)
    }
  }

  const dataSource: EnvVarRecord[] = Object.entries(envVars).map(([k, v]) => ({ key: k, value: v }))

  const columns = [
    {
      title: '变量名', dataIndex: 'key', key: 'key', width: '35%',
      render: (k: string) => <Text code style={{ fontSize: 13 }}>{k}</Text>,
    },
    {
      title: '变量值', dataIndex: 'value', key: 'value', width: '40%',
      render: (v: string, r: EnvVarRecord) =>
        editingKey === r.key ? (
          <Input size="small" value={editVal} onChange={e => setEditVal(e.target.value)}
            onPressEnter={() => handleSaveEdit(r.key)} style={{ width: '100%' }} autoFocus />
        ) : (
          <Text ellipsis={{ tooltip: v }} style={{ maxWidth: 200, fontFamily: 'monospace', fontSize: 12 }}>
            {v}
          </Text>
        ),
    },
    {
      title: '操作', key: 'action', width: '25%',
      render: (_: any, r: EnvVarRecord) =>
        editingKey === r.key ? (
          <Space size={4}>
            <Button type="link" size="small" onClick={() => handleSaveEdit(r.key)}>保存</Button>
            <Button type="link" size="small" onClick={() => setEditingKey(null)}>取消</Button>
          </Space>
        ) : (
          <Space size={4}>
            <Tooltip title="编辑值">
              <Button type="link" size="small" icon={<EditOutlined />}
                onClick={() => { setEditingKey(r.key); setEditVal(r.value) }} />
            </Tooltip>
            <Popconfirm title={`确定删除 ${r.key}？`} onConfirm={() => handleDelete(r.key)}
              okText="确定" cancelText="取消">
              <Tooltip title="删除">
                <Button type="link" size="small" danger icon={<DeleteOutlined />} />
              </Tooltip>
            </Popconfirm>
          </Space>
        ),
    },
  ]

  return (
    <Modal
      title={
        <Space>
          <WarningOutlined style={{ color: '#faad14' }} />
          <span style={{ fontWeight: 600 }}>环境变量审核</span>
        </Space>
      }
      open={open}
      onCancel={onClose}
      width={680}
      footer={
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Text type="secondary">共 {dataSource.length} 个环境变量</Text>
          <Space>
            <Button onClick={onClose}>关闭</Button>
            <Button type="primary" size="large" icon={<CheckCircleOutlined />}
              loading={confirming} onClick={handleConfirm} disabled={dataSource.length === 0}>
              确认并继续部署
            </Button>
          </Space>
        </Space>
      }
    >
      <Alert type="info" showIcon style={{ marginBottom: 16 }}
        message="请审核以下环境变量，这些变量将被注入到容器运行环境中。您可以修改变量值、添加新变量或删除不需要的变量。" />

      <Table columns={columns} dataSource={dataSource} loading={loading}
        rowKey="key" pagination={false} size="small"
        locale={{ emptyText: <Empty description="暂无环境变量" /> }} />

      {showAdd ? (
        <div style={{ marginTop: 12, padding: 12, background: '#fafafa', borderRadius: 6, border: '1px dashed #d9d9d9' }}>
          <Space direction="vertical" style={{ width: '100%' }} size={8}>
            <Text strong style={{ fontSize: 13 }}>添加环境变量</Text>
            <Input placeholder="变量名（如 DATABASE_URL）" value={newKey}
              onChange={e => setNewKey(e.target.value)} onPressEnter={handleAdd} />
            <Input placeholder="变量值" value={newValue}
              onChange={e => setNewValue(e.target.value)} onPressEnter={handleAdd} />
            <Space>
              <Button type="primary" size="small" onClick={handleAdd}>添加</Button>
              <Button size="small" onClick={() => { setShowAdd(false); setNewKey(''); setNewValue('') }}>取消</Button>
            </Space>
          </Space>
        </div>
      ) : (
        <Button type="dashed" block icon={<PlusOutlined />} style={{ marginTop: 12 }}
          onClick={() => setShowAdd(true)}>添加环境变量</Button>
      )}

      <div style={{ marginTop: 16 }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          <strong>提示：</strong>修改变量值后需点击「保存」按钮。确认后部署将自动继续执行。
        </Text>
      </div>
    </Modal>
  )
}

export default EnvVarReviewModal
