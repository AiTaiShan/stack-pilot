import React, { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Card, Descriptions, Button, Table, Space, message, Modal, Select, Form, Input, Tag, Tooltip, Drawer, Popconfirm } from 'antd'
import { EyeOutlined, StopOutlined, RedoOutlined } from '@ant-design/icons'
import client from '../api/client'
import DeploymentProgress from '../components/DeploymentProgress'

const statusColors: Record<string, string> = {
  pending: 'default',
  running: 'processing',
  paused: 'warning',
  cancelled: 'default',
  success: 'success',
  failed: 'error',
  rolling_back: 'warning',
  rolled_back: 'default',
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
}

const ProjectDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const [project, setProject] = useState<any>(null)
  const [deployments, setDeployments] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [deployModalVisible, setDeployModalVisible] = useState(false)
  const [editModalVisible, setEditModalVisible] = useState(false)
  const [branch, setBranch] = useState<string>('')
  const [platform, setPlatform] = useState<string>('local')
  const [branches, setBranches] = useState<string[]>([])
  const [branchesLoading, setBranchesLoading] = useState(false)
  const [editForm] = Form.useForm()
  const [activeDeployment, setActiveDeployment] = useState<any>(null)
  const [drawerVisible, setDrawerVisible] = useState(false)
  const [selectedDeployment, setSelectedDeployment] = useState<any>(null)

  const fetchData = async () => {
    setLoading(true)
    try {
      const [projectRes, deploymentsRes] = await Promise.all([
        client.get(`/projects/${id}`),
        client.get(`/deployments/?project_id=${id}`)
      ])
      setProject(projectRes.data.data)
      const deps = deploymentsRes.data.data.items || []
      setDeployments(deps)

      // 找到正在执行的部署
      const running = deps.find((d: any) => d.status === 'running' || d.status === 'paused')
      setActiveDeployment(running || null)
    } catch (error) {
      message.error('获取项目信息失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()

    // 定期刷新部署列表（检测新的活跃部署）
    const interval = setInterval(fetchData, 10000)

    return () => clearInterval(interval)
  }, [id])

  const fetchBranches = async () => {
    if (!id) return
    setBranchesLoading(true)
    try {
      const res = await client.get(`/projects/${id}/branches`)
      const branchList = res.data.data.branches || []
      const defaultBranch = res.data.data.default_branch || 'main'
      setBranches(branchList)
      setBranch(defaultBranch)
    } catch (error) {
      message.error('获取分支列表失败')
      setBranches(['main'])
      setBranch('main')
    } finally {
      setBranchesLoading(false)
    }
  }

  const openDeployModal = () => {
    setDeployModalVisible(true)
    fetchBranches()
  }

  const openEditModal = async () => {
    setEditModalVisible(true)
    setBranchesLoading(true)
    try {
      const res = await client.get(`/projects/${id}/branches`)
      setBranches(res.data.data.branches || [])
    } catch (error) {
      setBranches([])
    } finally {
      setBranchesLoading(false)
    }
    editForm.setFieldsValue({
      name: project.name,
      description: project.description,
      default_branch: project.default_branch,
    })
  }

  const handleEdit = async (values: { name: string; description?: string; default_branch: string }) => {
    try {
      await client.put(`/projects/${id}`, values)
      message.success('项目更新成功')
      setEditModalVisible(false)
      fetchData()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '更新失败')
    }
  }

  const handleDeploy = async (values: { branch: string; platform: string }) => {
    try {
      await client.post('/deployments/', {
        git_url: project.git_url,
        branch: values.branch,
        platform: values.platform,
        config: { project_id: id }
      })
      message.success('部署已触发')
      setDeployModalVisible(false)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '部署失败')
    }
  }

  const formatDate = (dateStr: string) => {
    if (!dateStr) return '-'
    const d = new Date(dateStr)
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
  }

  const openDrawer = (deployment: any) => {
    setSelectedDeployment(deployment)
    setDrawerVisible(true)
  }

  const handleCancel = async (deploymentId: string) => {
    try {
      await client.post(`/deployments/${deploymentId}/cancel`)
      message.success('部署已终止')
      fetchData()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '终止失败')
    }
  }

  const handleRedeploy = async (record: any) => {
    try {
      await client.post('/deployments/', {
        git_url: project.git_url,
        branch: record.branch,
        platform: record.platform,
        config: { project_id: id }
      })
      message.success('重新部署已触发')
      fetchData()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '重新部署失败')
    }
  }

  // 刷新选中的部署状态
  useEffect(() => {
    if (!drawerVisible || !selectedDeployment) return

    const isRunning = selectedDeployment.status === 'running' || selectedDeployment.status === 'paused'
    if (!isRunning) return

    const interval = setInterval(async () => {
      try {
        const res = await client.get(`/deployments/${selectedDeployment.id}/status`)
        const updated = res.data.data
        setSelectedDeployment((prev: any) => prev ? { ...prev, ...updated } : null)

        // 同时刷新部署列表
        fetchData()

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

  const deploymentColumns = [
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (status: string) => (
        <Tag color={statusColors[status] || 'default'}>
          {statusLabels[status] || status}
        </Tag>
      )
    },
    { title: '平台', dataIndex: 'platform', key: 'platform', width: 80 },
    { title: '分支', dataIndex: 'branch', key: 'branch', width: 100 },
    { title: '部署URL', dataIndex: 'deploy_url', key: 'deploy_url', ellipsis: true },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 180, render: (text: string) => formatDate(text) },
    {
      title: '操作', key: 'action', width: 180, fixed: 'right',
      render: (_: any, record: any) => (
        <Space size={4}>
          <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => openDrawer(record)}>
            详情
          </Button>
          {(record.status === 'running' || record.status === 'paused') && (
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
    },
  ]

  if (!project) return <div>加载中...</div>

  return (
    <div>
      <Card title="项目详情" extra={
        <Space>
          <Button onClick={openEditModal}>编辑</Button>
          <Tooltip title={activeDeployment ? '有部署正在执行中，请等待完成后再试' : ''}>
            <Button
              type="primary"
              onClick={openDeployModal}
              disabled={!!activeDeployment}
              loading={!!activeDeployment}
            >
              {activeDeployment ? '部署中' : '触发部署'}
            </Button>
          </Tooltip>
        </Space>
      }>
        <Descriptions column={2}>
          <Descriptions.Item label="项目名称">{project.name}</Descriptions.Item>
          <Descriptions.Item label="Git地址">{project.git_url}</Descriptions.Item>
          <Descriptions.Item label="默认分支">{project.default_branch}</Descriptions.Item>
          <Descriptions.Item label="创建时间">{formatDate(project.created_at)}</Descriptions.Item>
          <Descriptions.Item label="描述" span={2}>{project.description || '无'}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="部署记录" style={{ marginTop: 16 }}>
        <Table columns={deploymentColumns} dataSource={deployments} loading={loading} rowKey="id" />
      </Card>

      <Modal title="编辑项目" open={editModalVisible} onCancel={() => setEditModalVisible(false)} onOk={() => editForm.submit()}>
        <Form form={editForm} onFinish={handleEdit} layout="vertical">
          <Form.Item name="name" label="项目名称" rules={[{ required: true, message: '请输入项目名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="default_branch" label="默认分支" rules={[{ required: true, message: '请选择默认分支' }]}>
            <Select loading={branchesLoading} notFoundContent={branchesLoading ? '加载中...' : '暂无分支'}>
              {branches.map((b) => (
                <Select.Option key={b} value={b}>{b}</Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="description" label="项目描述">
            <Input.TextArea />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title="触发部署" open={deployModalVisible} onCancel={() => setDeployModalVisible(false)} onOk={() => handleDeploy({ branch, platform })}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Select
            placeholder="选择分支"
            style={{ width: '100%' }}
            value={branch || undefined}
            onChange={(val) => setBranch(val)}
            loading={branchesLoading}
            notFoundContent={branchesLoading ? '加载中...' : '暂无分支'}
          >
            {branches.map((b) => (
              <Select.Option key={b} value={b}>{b}</Select.Option>
            ))}
          </Select>
          <Select placeholder="选择平台" style={{ width: '100%' }} value={platform} onChange={(val) => setPlatform(val)}>
            <Select.Option value="local">本地部署</Select.Option>
            <Select.Option value="k8s">Kubernetes</Select.Option>
            <Select.Option value="coolify">Coolify</Select.Option>
          </Select>
        </Space>
      </Modal>

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
    </div>
  )
}

export default ProjectDetail
