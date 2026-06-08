import React, { useEffect, useState } from 'react'
import { Table, Tag, Space, message, Button, Popconfirm, Drawer, Modal, Spin, Typography, List } from 'antd'
import type { ColumnType } from 'antd/es/table/interface'
import { StopOutlined, RedoOutlined, EyeOutlined, BugOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons'
import client from '../api/client'
import DeploymentProgress from '../components/DeploymentProgress'
import EnvVarReviewModal from '../components/EnvVarReviewModal'

const { Text, Paragraph, Title } = Typography

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

  // 诊断相关状态
  const [diagnoseVisible, setDiagnoseVisible] = useState(false)
  const [diagnoseLoading, setDiagnoseLoading] = useState(false)
  const [diagnoseResult, setDiagnoseResult] = useState<any>(null)

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
        project_id: record.project_id,
        git_url: record.git_url,
        branch: record.branch,
        platform: record.platform,
      })
      message.success('重新部署已触发')
      fetchDeployments()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '重新部署失败')
    }
  }

  // 查看诊断结果（从日志中获取，诊断是自动执行的）
  const handleDiagnose = async (record: any) => {
    setDiagnoseVisible(true)
    setDiagnoseLoading(true)
    setDiagnoseResult(null)
    try {
      // 从部署日志中获取诊断结果
      const res = await client.get(`/deployments/${record.id}/logs`)
      const logs = res.data.data?.items || []
      const diagnoseLog = logs.find((log: any) => log.step === 'diagnose')

      if (diagnoseLog) {
        // 解析诊断日志内容
        const message = diagnoseLog.message
        const diagnosisMatch = message.match(/AI 诊断[：:]\s*(.+?)(?:\n建议|$)/s)
        const suggestionsMatch = message.match(/建议[：:]\s*(.+?)$/s)

        setDiagnoseResult({
          step_name: record.current_step || '未知',
          error_message: record.error_message || '未知错误',
          diagnosis: diagnosisMatch ? diagnosisMatch[1].trim() : message,
          suggestions: suggestionsMatch ? suggestionsMatch[1].split(';').map((s: string) => s.trim()) : [],
          retryable: false
        })
      } else {
        // 没有诊断日志，显示基本信息
        setDiagnoseResult({
          step_name: record.current_step || '未知',
          error_message: record.error_message || '未知错误',
          diagnosis: '暂无 AI 诊断结果，部署可能因代码或基础设施问题失败',
          suggestions: ['检查部署日志获取详细错误信息', '确认代码无语法错误', '检查网络连接和资源可用性'],
          retryable: false
        })
      }
    } catch (error: any) {
      message.error('获取诊断结果失败')
      setDiagnoseVisible(false)
    } finally {
      setDiagnoseLoading(false)
    }
  }

  const columns: ColumnType<any>[] = [
    { title: '项目', dataIndex: 'project_name', key: 'project_name', width: 120, ellipsis: true },
    { title: '部署ID', dataIndex: 'id', key: 'id', width: 90, ellipsis: true },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90, align: 'center',
      render: (status: string) => <Tag color={statusColors[status] || 'default'}>{statusLabels[status] || status}</Tag>
    },
    { title: '平台', dataIndex: 'platform', key: 'platform', width: 80, align: 'center' },
    { title: '部署URL', dataIndex: 'deploy_url', key: 'deploy_url', width: 150, ellipsis: true },
    {
      title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 160,
      sorter: (a: any, b: any) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
      render: (text: string) => formatDate(text)
    },
    {
      title: '操作', key: 'action', width: 180, fixed: 'right',
      render: (_: any, record: any) => (
        <div style={{ display: 'flex', gap: 2, flexWrap: 'nowrap' }}>
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
          {record.status === 'failed' && (
            <Button type="link" size="small" icon={<BugOutlined />} style={{ color: '#722ed1' }} onClick={() => handleDiagnose(record)}>
              分析
            </Button>
          )}
        </div>
      )
    }
  ]

  return (
    <div>
      <h2>部署记录</h2>
      <Table
        columns={columns}
        dataSource={deployments}
        loading={loading}
        rowKey="id"
        size="middle"
        scroll={{ x: 900 }}
        pagination={{
          pageSize: 10,
          showSizeChanger: true,
          showQuickJumper: true,
          showTotal: (total) => `共 ${total} 条记录`,
        }}
      />

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

      {/* 诊断结果弹窗 */}
      <Modal
        title={
          <Space>
            <BugOutlined style={{ color: '#722ed1' }} />
            <span>AI 故障诊断</span>
          </Space>
        }
        open={diagnoseVisible}
        onCancel={() => setDiagnoseVisible(false)}
        footer={[
          <Button key="close" onClick={() => setDiagnoseVisible(false)}>
            关闭
          </Button>,
          diagnoseResult?.retryable && (
            <Button key="retry" type="primary" onClick={() => {
              setDiagnoseVisible(false)
              // 找到对应的部署记录并重试
              const dep = deployments.find(d => d.id === diagnoseResult?.deployment_id)
              if (dep) handleRedeploy(dep)
            }}>
              重试部署
            </Button>
          )
        ]}
        width={600}
      >
        {diagnoseLoading ? (
          <div style={{ textAlign: 'center', padding: '40px 0' }}>
            <Spin size="large" />
            <div style={{ marginTop: 16 }}>正在分析部署失败原因...</div>
          </div>
        ) : diagnoseResult ? (
          <div>
            {/* 失败信息 */}
            <div style={{ marginBottom: 16, padding: 12, background: '#fff2f0', borderRadius: 6, border: '1px solid #ffccc7' }}>
              <Text strong>失败步骤: </Text>
              <Tag color="red">{diagnoseResult.step_name}</Tag>
              <br />
              <Text strong>错误信息: </Text>
              <Text type="danger">{diagnoseResult.error_message}</Text>
            </div>

            {/* 诊断结果 */}
            <div style={{ marginBottom: 16 }}>
              <Title level={5}>📋 诊断结果</Title>
              <Paragraph>{diagnoseResult.diagnosis}</Paragraph>
            </div>

            {/* 修复建议 */}
            {diagnoseResult.suggestions?.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <Title level={5}>💡 修复建议</Title>
                <List
                  size="small"
                  dataSource={diagnoseResult.suggestions}
                  renderItem={(item: string, index: number) => (
                    <List.Item>
                      <Text>{index + 1}. {item}</Text>
                    </List.Item>
                  )}
                />
              </div>
            )}

            {/* 是否可重试 */}
            <div style={{ padding: 12, background: '#f6ffed', borderRadius: 6, border: '1px solid #b7eb8f' }}>
              {diagnoseResult.retryable ? (
                <Space>
                  <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 16 }} />
                  <Text>此问题可以通过重试解决</Text>
                </Space>
              ) : (
                <Space>
                  <CloseCircleOutlined style={{ color: '#ff4d4f', fontSize: 16 }} />
                  <Text>此问题需要手动修复后才能重试</Text>
                </Space>
              )}
            </div>
          </div>
        ) : null}
      </Modal>
    </div>
  )
}

export default Deployments
