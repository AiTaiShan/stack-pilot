import React, { useEffect, useState } from 'react'
import { Modal, Button, Input, Space, message, Alert, Spin } from 'antd'
import { EditOutlined, SaveOutlined, CheckCircleOutlined } from '@ant-design/icons'
import client from '../api/client'

interface Props {
  deploymentId: string
  open: boolean
  onClose: () => void
  onConfirmed: () => void
}

const EnvVarReviewModal: React.FC<Props> = ({
  deploymentId, open, onClose, onConfirmed,
}) => {
  const [content, setContent] = useState('')
  const [editing, setEditing] = useState(false)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [confirming, setConfirming] = useState(false)

  // 获取文件内容
  const fetchContent = async () => {
    setLoading(true)
    try {
      const res = await client.get(`/deployments/${deploymentId}/compose-file`)
      setContent(res.data.data.content)
    } catch (err: any) {
      const msg = err.response?.data?.detail || '获取文件失败'
      message.error(msg)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (open) {
      setEditing(false)
      fetchContent()
    }
  }, [open, deploymentId])

  // 保存文件内容
  const handleSave = async () => {
    setSaving(true)
    try {
      await client.put(`/deployments/${deploymentId}/compose-file`, { content })
      message.success('保存成功')
      setEditing(false)
    } catch (err: any) {
      const msg = err.response?.data?.detail || '保存失败'
      message.error(msg)
    } finally {
      setSaving(false)
    }
  }

  // 确认审核
  const handleConfirm = async () => {
    setConfirming(true)
    try {
      await client.post(`/deployments/${deploymentId}/confirm-env-vars`)
      message.success('已确认，部署继续')
      onConfirmed()
    } catch (err: any) {
      const msg = err.response?.data?.detail || '确认失败'
      message.error(msg)
    } finally {
      setConfirming(false)
    }
  }

  return (
    <Modal
      title="环境变量审核"
      open={open}
      onCancel={onClose}
      width={800}
      footer={
        <Space>
          <Button onClick={onClose}>关闭</Button>
          <Button
            icon={<EditOutlined />}
            onClick={() => {
              if (editing) {
                // 取消编辑时重新获取原始内容
                fetchContent()
              }
              setEditing(!editing)
            }}
          >
            {editing ? '取消编辑' : '编辑'}
          </Button>
          <Button
            type="primary"
            icon={<SaveOutlined />}
            onClick={handleSave}
            disabled={!editing}
            loading={saving}
          >
            保存
          </Button>
          <Button
            type="primary"
            icon={<CheckCircleOutlined />}
            onClick={handleConfirm}
            loading={confirming}
            disabled={editing}
          >
            确认并继续部署
          </Button>
        </Space>
      }
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="请审核 docker-compose.yml 文件内容，确认后部署将自动继续执行。"
      />

      {loading ? (
        <div style={{ textAlign: 'center', padding: '40px 0' }}>
          <Spin tip="加载中..." />
        </div>
      ) : (
        <Input.TextArea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          disabled={!editing}
          rows={20}
          style={{ fontFamily: 'monospace', fontSize: 13 }}
        />
      )}
    </Modal>
  )
}

export default EnvVarReviewModal
