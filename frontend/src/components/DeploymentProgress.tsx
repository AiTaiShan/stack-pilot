import React, { useEffect, useState } from 'react'
import { Card, Steps, Tag, Collapse, Timeline, Typography, Spin } from 'antd'
import {
  LoadingOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  SyncOutlined,
} from '@ant-design/icons'
import client from '../api/client'

const { Text } = Typography

interface StepInfo {
  key: string
  title: string
  description: string
}

interface LogEntry {
  timestamp: string
  level: string
  message: string
  step?: string
}

const STEPS: StepInfo[] = [
  { key: 'clone', title: '克隆代码', description: '从 Git 仓库拉取代码' },
  { key: 'generate_review', title: '生成部署文件', description: '生成 Dockerfile 并 AI 审核' },
  { key: 'build', title: '构建镜像', description: '构建 Docker 镜像' },
  { key: 'env_review', title: '环境变量审核', description: '审核并确认容器环境变量' },
  { key: 'push', title: '推送镜像', description: '推送镜像到仓库' },
  { key: 'deploy', title: '部署应用', description: '部署容器到目标环境' },
  { key: 'configure', title: '配置服务', description: '配置网络和域名' },
  { key: 'verify', title: '验证部署', description: '检查服务健康状态' },
]

const statusColors: Record<string, string> = {
  running: 'processing',
  success: 'success',
  failed: 'error',
  paused: 'warning',
  pending: 'default',
  waiting_review: 'warning',
}

const statusLabels: Record<string, string> = {
  running: '执行中',
  success: '成功',
  failed: '失败',
  paused: '已暂停',
  pending: '等待中',
  waiting_review: '等待审核',
}

interface DeploymentProgressProps {
  deploymentId: string
  status: string
  currentStep?: string
  progress?: number
  showCard?: boolean
}

const DeploymentProgress: React.FC<DeploymentProgressProps> = ({
  deploymentId,
  status,
  currentStep,
  progress,
  showCard = true,
}) => {
  const [logs, setLogs] = useState<LogEntry[]>([])

  useEffect(() => {
    if (status === 'running' || status === 'paused' || status === 'waiting_review') {
      fetchLogs()
      const interval = setInterval(fetchLogs, 3000)
      return () => clearInterval(interval)
    } else if (status === 'success' || status === 'failed') {
      fetchLogs()
    }
  }, [deploymentId, status])

  const fetchLogs = async () => {
    try {
      const res = await client.get(`/deployments/${deploymentId}/logs`)
      setLogs(res.data.data?.logs || [])
    } catch (error) {
      console.error('获取日志失败:', error)
    }
  }

  const getStepStatus = (stepKey: string): 'wait' | 'process' | 'finish' | 'error' => {
    // 部署成功 → 所有步骤标记为完成
    if (status === 'success') return 'finish'

    if (!currentStep) return 'wait'

    const currentIdx = STEPS.findIndex((s) => s.key === currentStep)
    const stepIdx = STEPS.findIndex((s) => s.key === stepKey)

    if (status === 'failed' && stepKey === currentStep) return 'error'
    if (stepIdx < currentIdx) return 'finish'
    if (stepIdx === currentIdx) return 'process'
    return 'wait'
  }

  const getStepIcon = (stepKey: string) => {
    if (stepKey === 'env_review' && status === 'waiting_review') {
      return <ClockCircleOutlined style={{ color: '#faad14' }} />
    }
    const stepStatus = getStepStatus(stepKey)
    if (stepStatus === 'finish') return <CheckCircleOutlined style={{ color: '#52c41a' }} />
    if (stepStatus === 'process') return <LoadingOutlined style={{ color: '#1890ff' }} />
    if (stepStatus === 'error') return <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
    return <ClockCircleOutlined style={{ color: '#d9d9d9' }} />
  }

  const formatTime = (timestamp: string) => {
    if (!timestamp) return ''
    const d = new Date(timestamp)
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
  }

  const getStepLogs = (stepKey: string) => {
    return logs.filter((log) => log.step === stepKey)
  }

  const content = (
    <>
      <div style={{ marginBottom: 16 }}>
        <Text strong>部署状态: </Text>
        {statusColors[status] && statusLabels[status] && (
          <Tag
            icon={
              status === 'running' ? <SyncOutlined spin /> :
              status === 'success' ? <CheckCircleOutlined /> :
              status === 'failed' ? <CloseCircleOutlined /> :
              status === 'waiting_review' ? <ClockCircleOutlined /> :
              undefined
            }
            color={statusColors[status]}
          >
            {statusLabels[status]}
          </Tag>
        )}
      </div>

      <Steps
        current={STEPS.findIndex((s) => s.key === currentStep)}
        status={status === 'failed' ? 'error' : undefined}
        direction="vertical"
        size="small"
        items={STEPS.map((step) => ({
          title: step.title,
          description: (
            <div>
              <div>{step.description}</div>
              {step.key === 'env_review' && status === 'waiting_review' && (
                <div style={{ marginTop: 4 }}>
                  <ClockCircleOutlined style={{ color: '#faad14', marginRight: 4 }} />
                  <Text type="warning">等待审核环境变量...</Text>
                </div>
              )}
              {getStepStatus(step.key) === 'process' && !(step.key === 'env_review' && status === 'waiting_review') && (
                <div style={{ marginTop: 4 }}>
                  <Spin size="small" /> <Text type="secondary">执行中...</Text>
                </div>
              )}
            </div>
          ),
          icon: getStepIcon(step.key),
        }))}
      />

      <Collapse
        ghost
        style={{ marginTop: 16 }}
        items={STEPS.map((step) => ({
          key: step.key,
          label: (
            <span>
              {getStepIcon(step.key)}{' '}
              <Text strong={getStepStatus(step.key) === 'process'}>
                {step.title}
              </Text>
              {step.key === 'env_review' && status === 'waiting_review' && (
                <Tag color="warning" style={{ marginLeft: 8 }}>
                  等待审核
                </Tag>
              )}
              {getStepStatus(step.key) === 'process' && !(step.key === 'env_review' && status === 'waiting_review') && (
                <Tag color="processing" style={{ marginLeft: 8 }}>
                  进行中
                </Tag>
              )}
              {getStepStatus(step.key) === 'finish' && (
                <Tag color="success" style={{ marginLeft: 8 }}>
                  完成
                </Tag>
              )}
              {getStepStatus(step.key) === 'error' && (
                <Tag color="error" style={{ marginLeft: 8 }}>
                  失败
                </Tag>
              )}
            </span>
          ),
          children: (
            <div style={{ maxHeight: 300, overflow: 'auto' }}>
              {getStepLogs(step.key).length > 0 ? (
                <Timeline
                  items={getStepLogs(step.key).map((log) => ({
                    color: log.level === 'error' ? 'red' : log.level === 'warning' ? 'orange' : 'blue',
                    children: (
                      <div>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {formatTime(log.timestamp)}
                        </Text>
                        <br />
                        <Text>{log.message}</Text>
                      </div>
                    ),
                  }))}
                />
              ) : (
                <Text type="secondary">
                  {getStepStatus(step.key) === 'wait' ? '等待执行' : '暂无日志'}
                </Text>
              )}
            </div>
          ),
        }))}
      />

      {progress !== undefined && (
        <div style={{ marginTop: 16, textAlign: 'right' }}>
          <Text type="secondary">总进度: {progress}%</Text>
        </div>
      )}
    </>
  )

  if (showCard) {
    return (
      <Card title="部署进度" style={{ marginTop: 16 }}>
        {content}
      </Card>
    )
  }

  return content
}

export default DeploymentProgress
