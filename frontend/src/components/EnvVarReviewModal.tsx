import React, { useEffect, useState, useCallback } from 'react'
import {
  Modal, Table, Button, Input, Space, message, Tooltip,
  Popconfirm, Typography, Alert, Empty, Tabs,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined,
  CheckCircleOutlined, WarningOutlined,
} from '@ant-design/icons'
import client from '../api/client'

const { Text } = Typography

interface EnvVarItem {
  value: string
  source: string
}

interface ServiceEnvVars {
  env_vars: Record<string, EnvVarItem>
}

interface GroupedEnvVars {
  [serviceName: string]: ServiceEnvVars
}

interface EnvVarRecord {
  key: string
  value: string
  source: string
}

interface Props {
  deploymentId: string
  open: boolean
  onClose: () => void
  onConfirmed: () => void
}

/** 服务名显示映射 */
const SERVICE_LABEL_MAP: Record<string, string> = {
  app: '应用服务',
}

const getServiceLabel = (name: string): string =>
  SERVICE_LABEL_MAP[name] || name

const EnvVarReviewModal: React.FC<Props> = ({
  deploymentId, open, onClose, onConfirmed,
}) => {
  const [groupedEnvVars, setGroupedEnvVars] = useState<GroupedEnvVars>({})
  const [loading, setLoading] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [activeTab, setActiveTab] = useState<string>('')

  // 添加相关状态
  const [showAdd, setShowAdd] = useState(false)
  const [newKey, setNewKey] = useState('')
  const [newValue, setNewValue] = useState('')

  // 编辑相关状态
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [editVal, setEditVal] = useState('')

  const fetchVars = useCallback(async () => {
    setLoading(true)
    try {
      const res = await client.get(`/deployments/${deploymentId}/env-vars`)
      const data: GroupedEnvVars = res.data.data?.grouped_env_vars || {}
      setGroupedEnvVars(data)
      // 如果当前没有活跃 tab 或者活跃 tab 已不存在，设为第一个
      const keys = Object.keys(data)
      if (keys.length > 0 && !keys.includes(activeTab)) {
        setActiveTab(keys[0])
      }
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail || '获取环境变量失败'
      message.error(msg)
    } finally {
      setLoading(false)
    }
  }, [deploymentId, activeTab])

  useEffect(() => {
    if (open) {
      setActiveTab('')
      setShowAdd(false)
      setEditingKey(null)
      fetchVars()
    }
  }, [open]) // intentionally not including fetchVars

  const handleAdd = async () => {
    if (!newKey.trim() || !newValue.trim()) {
      message.warning('请填写变量名和变量值')
      return
    }
    try {
      await client.put(
        `/deployments/${deploymentId}/env-vars?service_name=${activeTab}`,
        { [newKey.trim()]: newValue.trim() },
      )
      setNewKey('')
      setNewValue('')
      setShowAdd(false)
      message.success('已添加')
      await fetchVars()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail || '添加失败'
      message.error(msg)
    }
  }

  const handleDelete = async (varName: string) => {
    try {
      await client.delete(
        `/deployments/${deploymentId}/env-vars/${activeTab}/${varName}`,
      )
      message.success(`已删除 ${varName}`)
      await fetchVars()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail || '删除失败'
      message.error(msg)
    }
  }

  const handleSaveEdit = async (varName: string) => {
    if (!editVal.trim()) {
      message.warning('请输入变量值')
      return
    }
    try {
      await client.put(
        `/deployments/${deploymentId}/env-vars?service_name=${activeTab}`,
        { [varName]: editVal.trim() },
      )
      setEditingKey(null)
      message.success('已更新')
      await fetchVars()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail || '更新失败'
      message.error(msg)
    }
  }

  const handleConfirm = async () => {
    setConfirming(true)
    try {
      await client.post(`/deployments/${deploymentId}/confirm-env-vars`)
      message.success('环境变量已确认，部署继续')
      onConfirmed()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail || '确认失败'
      message.error(msg)
    } finally {
      setConfirming(false)
    }
  }

  /** 当前活跃 tab 下的环境变量列表 */
  const currentEnvVars = groupedEnvVars[activeTab]?.env_vars || {}
  const dataSource: EnvVarRecord[] = Object.entries(currentEnvVars).map(
    ([k, v]) => ({ key: k, value: v.value, source: v.source }),
  )

  const totalCount = Object.values(groupedEnvVars).reduce(
    (sum, svc) => sum + Object.keys(svc.env_vars || {}).length, 0,
  )

  const columns = [
    {
      title: '变量名',
      dataIndex: 'key',
      key: 'key',
      width: '25%',
      render: (k: string) => <Text code style={{ fontSize: 13 }}>{k}</Text>,
    },
    {
      title: '变量值',
      dataIndex: 'value',
      key: 'value',
      width: '35%',
      render: (v: string, r: EnvVarRecord) =>
        editingKey === r.key ? (
          <Input
            size="small"
            value={editVal}
            onChange={e => setEditVal(e.target.value)}
            onPressEnter={() => handleSaveEdit(r.key)}
            style={{ width: '100%' }}
            autoFocus
          />
        ) : (
          <Text
            ellipsis={{ tooltip: v }}
            style={{ maxWidth: 200, fontFamily: 'monospace', fontSize: 12 }}
          >
            {v}
          </Text>
        ),
    },
    {
      title: '来源',
      dataIndex: 'source',
      key: 'source',
      width: '20%',
      render: (s: string) => (
        <Tooltip title={s}>
          <Text type="secondary" ellipsis style={{ maxWidth: 150, fontSize: 12 }}>
            {s || '-'}
          </Text>
        </Tooltip>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: '20%',
      render: (_: unknown, r: EnvVarRecord) =>
        editingKey === r.key ? (
          <Space size={4}>
            <Button type="link" size="small" onClick={() => handleSaveEdit(r.key)}>
              保存
            </Button>
            <Button type="link" size="small" onClick={() => setEditingKey(null)}>
              取消
            </Button>
          </Space>
        ) : (
          <Space size={4}>
            <Tooltip title="编辑值">
              <Button
                type="link"
                size="small"
                icon={<EditOutlined />}
                onClick={() => { setEditingKey(r.key); setEditVal(r.value) }}
              />
            </Tooltip>
            <Popconfirm
              title={`确定删除 ${r.key}？`}
              onConfirm={() => handleDelete(r.key)}
              okText="确定"
              cancelText="取消"
            >
              <Tooltip title="删除">
                <Button type="link" size="small" danger icon={<DeleteOutlined />} />
              </Tooltip>
            </Popconfirm>
          </Space>
        ),
    },
  ]

  const tabItems = Object.keys(groupedEnvVars).map(serviceName => ({
    key: serviceName,
    label: getServiceLabel(serviceName),
    children: (
      <>
        <Table
          columns={columns}
          dataSource={dataSource}
          loading={loading}
          rowKey="key"
          pagination={false}
          size="small"
          locale={{ emptyText: <Empty description="暂无环境变量" /> }}
        />

        {showAdd && activeTab === serviceName ? (
          <div
            style={{
              marginTop: 12,
              padding: 12,
              background: '#fafafa',
              borderRadius: 6,
              border: '1px dashed #d9d9d9',
            }}
          >
            <Space direction="vertical" style={{ width: '100%' }} size={8}>
              <Text strong style={{ fontSize: 13 }}>添加环境变量</Text>
              <Input
                placeholder="变量名（如 DATABASE_URL）"
                value={newKey}
                onChange={e => setNewKey(e.target.value)}
                onPressEnter={handleAdd}
              />
              <Input
                placeholder="变量值"
                value={newValue}
                onChange={e => setNewValue(e.target.value)}
                onPressEnter={handleAdd}
              />
              <Space>
                <Button type="primary" size="small" onClick={handleAdd}>添加</Button>
                <Button
                  size="small"
                  onClick={() => { setShowAdd(false); setNewKey(''); setNewValue('') }}
                >
                  取消
                </Button>
              </Space>
            </Space>
          </div>
        ) : (
          <Button
            type="dashed"
            block
            icon={<PlusOutlined />}
            style={{ marginTop: 12 }}
            onClick={() => { setShowAdd(true); setNewKey(''); setNewValue('') }}
          >
            添加环境变量
          </Button>
        )}
      </>
    ),
  }))

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
      width={800}
      footer={
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Text type="secondary">
            共 {Object.keys(groupedEnvVars).length} 个服务，{totalCount} 个环境变量
          </Text>
          <Space>
            <Button onClick={onClose}>关闭</Button>
            <Button
              type="primary"
              size="large"
              icon={<CheckCircleOutlined />}
              loading={confirming}
              onClick={handleConfirm}
              disabled={totalCount === 0}
            >
              确认并继续部署
            </Button>
          </Space>
        </Space>
      }
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="请审核以下环境变量，这些变量将被注入到容器运行环境中。您可以修改变量值、添加新变量或删除不需要的变量。"
      />

      {Object.keys(groupedEnvVars).length === 0 && !loading ? (
        <Empty description="暂无环境变量" />
      ) : (
        <Tabs
          activeKey={activeTab}
          onChange={(key) => {
            setActiveTab(key)
            setShowAdd(false)
            setEditingKey(null)
          }}
          items={tabItems}
        />
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
