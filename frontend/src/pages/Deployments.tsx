import React, { useEffect, useState } from 'react'
import { Table, Tag, Space, message, Button, Popconfirm, Drawer } from 'antd'
import type { ColumnType } from 'antd/es/table/interface'
import { StopOutlined, RedoOutlined, EyeOutlined } from '@ant-design/icons'
import client from '../api/client'
import DeploymentProgress from '../components/DeploymentProgress'
import EnvVarReviewModal from '../components/EnvVarReviewModal'

const statusColors: Record<string, string> = {
  pending: 'default',
  running: 'processing',
  paused: 'warning',
  cancelled: 'default',
  success: 'success',
  failed: 'error',
  rolling_back: 'warning',
  rolled_back: 'default',
  waiting_review: 'warning',
}

const statusLabels: Record<string, string> = {
  pending: '等待中',
  running: '执行中',
  paused: '已暂停',
  cancelled: '已取消',
  success: '成功',
  failed: '失败',
  rolling_back: '回滚中',
  rolled_back: '已回滚',
  waiting_review: '等待审核',
}

const formatDate = (dateStr: string) => {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}

const Deployments: React.FC = () => {
  const [deployments, setDeployments] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [drawerVisible, setDrawerVisible] = useState(false)
  const [selectedDeployment, setSelectedDeployment] = useState<any>(null)
  const [envReviewOpen, setEnvReviewOpen] = useState(false)
  const [envReviewDeploymentId, setEnvReviewDeploymentId] = useState<string>('')

  const fetchDeployments = async () => {
    setLoading(true)
    try {
      const projectsRes = await client.get('/projects')
      const projects = projectsRes.data.data.items || []

      const deployResults = await Promise.all(
        projects.map((project: any) =>
          client.get(`/deployments?project_id=${project.id}`)
            .then(res => (res.data.data?.items || []).map((d: any) => ({ ...d, project_name: project.name })))
            .catch(() => [])
        )
      )
      const allDeployments = deployResults.flat()

      setDeployments(allDeployments)
    } catch (error) {
      message.error('获取部署记录失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchDeployments()
  }, [])

  const openDrawer = (deployment: any) => {
    setSelectedDeployment(deployment)
    setDrawerVisible(true)
  }

  // 刷新选中的部署状态
  useEffect(() => {
    if (!drawerVisible || !selectedDeployment) return

    const isRunning = selectedDeployment.status === 'running' || selectedDeployment.status === 'paused' || selectedDeployment.status === 'waiting_review'
    if (!isRunning) return

    const interval = setInterval(async () => {
      try {
        const res = await client.get(`/deployments/${selectedDeployment.id}/status`)
        const updated = res.data.data
        setSelectedDeployment((prev: any) => prev ? { ...prev, ...updated } : null)

        // 同时刷新部署列表
        fetchDeployments()

        // 如果部署完成或取消，停止刷新
        if (['success', 'failed', 'cancelled'].includes(updated.status)) {
          clearInterval(interval)
        }
      } catch (error) {
        console.error('刷新部署状态失败:', error)
      }
    }, 3000)

    return () => clearInterval(interval)
  }, [drawerVisible, selectedDeployment?.id, selectedDeployment?.status])

  const handleCancel = async (deploymentId: string) => {
    try {
      await client.post(`/deployments/${deploymentId}/cancel`)
      message.success('部署已终止')
      fetchDeployments()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '终止失败')
    }
  }

  // 全局轮询：检测列表中是否有 running 状态的部署
  useEffect(() => {
    const hasRunning = deployments.some(
      (d: any) => d.status === 'running' || d.status === 'paused',
    )
    if (!hasRunning) return

    const interval = setInterval(async () => {
      try {
        await fetchDeployments()
      } catch (error) {
        console.error('轮询部署列表失败:', error)
      }
    }, 5000)

    return () => clearInterval(interval)
  }, [deployments.length])

  const openEnvReview = (deployment: any) => {
    setEnvReviewDeploymentId(deployment.id)
    setEnvReviewOpen(true)
  }

  const handleReviewClose = () => {
    setEnvReviewOpen(false)
  }

  const handleReviewConfirmed = () => {
    setEnvReviewOpen(false)
    fetchDeployments()
  }

  const handleRedeploy = async (record: any) => {
    try {
      await client.post('/deployments', {
        git_url: record.git_url,
        branch: record.branch,
        platform: record.platform,
        config: { project_id: record.project_id }
      })
      message.success('重新部署已触发')
      fetchDeployments()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '重新部署失败')
    }
  }

  const columns: ColumnType<any>[] = [
    { title: '项目', dataIndex: 'project_name', key: 'project_name', width: 120 },
    { title: '部署ID', dataIndex: 'id', key: 'id', width: 100, ellipsis: true },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (status: string) => <Tag color={statusColors[status] || 'default'}>{statusLabels[status] || status}</Tag>
    },
    { title: '平台', dataIndex: 'platform', key: 'platform', width: 80 },
    { title: '部署URL', dataIndex: 'deploy_url', key: 'deploy_url', ellipsis: true },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 180, render: (text: string) => formatDate(text) },
    {
      title: '操作', key: 'action', width: 180, fixed: 'right',
      render: (_: any, record: any) => (
        <Space size={4}>
          <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => openDrawer(record)}>
            详情
          </Button>
          {record.status === 'waiting_review' && (
            <Button type="link" size="small" style={{ color: '#faad14' }} onClick={() => openEnvReview(record)}>
              审核
            </Button>
          )}
          {(record.status === 'running' || record.status === 'paused' || record.status === 'waiting_review') && (
            <Popconfirm
              title="确定要终止此部署吗？"
              onConfirm={() => handleCancel(record.id)}
              okText="确定"
              cancelText="取消"
            >
              <Button type="link" size="small" danger icon={<StopOutlined />}>
                终止
              </Button>
            </Popconfirm>
          )}
          {(record.status === 'success' || record.status === 'failed' || record.status === 'cancelled') && (
            <Button type="link" size="small" icon={<RedoOutlined />} onClick={() => handleRedeploy(record)}>
              重试
            </Button>
          )}
        </Space>
      )
    }
  ]

  return (
    <div>
      <h2>部署记录</h2>
      <Table columns={columns} dataSource={deployments} loading={loading} rowKey="id" />

      <Drawer
        title="部署详情"
        placement="right"
        width={600}
        open={drawerVisible}
        onClose={() => setDrawerVisible(false)}
      >
        {selectedDeployment && (
          <DeploymentProgress
            deploymentId={selectedDeployment.id}
            status={selectedDeployment.status}
            currentStep={selectedDeployment.current_step}
            progress={selectedDeployment.progress}
            showCard={false}
          />
        )}
      </Drawer>

      <EnvVarReviewModal
        deploymentId={envReviewDeploymentId}
        open={envReviewOpen}
        onClose={handleReviewClose}
        onConfirmed={handleReviewConfirmed}
      />
    </div>
  )
}

export default Deployments
