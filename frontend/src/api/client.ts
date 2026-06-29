import { API_BASE } from "../refactored/constants";

/**
 * API 客户端封装
 */
class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE) {
    this.baseUrl = baseUrl;
  }

  /**
   * 通用请求方法
   */
  private async request<T>(
    method: string,
    path: string,
    data?: any,
    params?: Record<string, string>
  ): Promise<T> {
    let url = `${this.baseUrl}${path}`;
    
    if (params) {
      const searchParams = new URLSearchParams();
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          searchParams.append(key, value);
        }
      });
      const queryString = searchParams.toString();
      if (queryString) {
        url += `?${queryString}`;
      }
    }

    const options: RequestInit = {
      method,
      headers: {
        "Content-Type": "application/json",
      },
    };

    if (data && (method === "POST" || method === "PUT" || method === "PATCH")) {
      options.body = JSON.stringify(data);
    }

    try {
      const response = await fetch(url, options);
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      console.error(`API request failed: ${method} ${url}`, error);
      throw error;
    }
  }

  /**
   * GET 请求
   */
  async get<T>(path: string, params?: Record<string, string>): Promise<T> {
    return this.request<T>("GET", path, undefined, params);
  }

  /**
   * POST 请求
   */
  async post<T>(path: string, data?: any, params?: Record<string, string>): Promise<T> {
    return this.request<T>("POST", path, data, params);
  }

  /**
   * PUT 请求
   */
  async put<T>(path: string, data?: any, params?: Record<string, string>): Promise<T> {
    return this.request<T>("PUT", path, data, params);
  }

  /**
   * DELETE 请求
   */
  async delete<T>(path: string, params?: Record<string, string>): Promise<T> {
    return this.request<T>("DELETE", path, undefined, params);
  }

  // ==================== 版本相关 ====================

  /**
   * 获取所有版本
   */
  async getVersions() {
    return this.get<any[]>("/api/versions");
  }

  /**
   * 创建版本
   */
  async createVersion(data: any) {
    return this.post<any>("/api/versions", data);
  }

  /**
   * 更新版本
   */
  async updateVersion(versionId: number, data: any) {
    return this.put<any>(`/api/versions/${versionId}`, data);
  }

  /**
   * 获取版本阶段
   */
  async getStages(versionId: number) {
    return this.get<any[]>(`/api/versions/${versionId}/stages`);
  }

  /**
   * 批量更新阶段
   */
  async batchUpdateStages(versionId: number, data: any) {
    return this.put<any>(`/api/versions/${versionId}/stages/batch`, data);
  }

  /**
   * 更新单个阶段
   */
  async updateStage(versionId: number, stageName: string, data: any) {
    return this.put<any>(`/api/versions/${versionId}/stages/${stageName}`, data);
  }

  // ==================== Jira 相关 ====================

  /**
   * 保存Jira凭据
   */
  async saveCredential(versionId: number, data: any) {
    return this.post<any>(`/api/versions/${versionId}/credential`, data);
  }

  /**
   * 获取凭据状态
   */
  async getCredentialStatus(versionId: number) {
    return this.get<any>(`/api/versions/${versionId}/credential/status`);
  }

  /**
   * 删除凭据
   */
  async deleteCredential(versionId: number) {
    return this.delete<any>(`/api/versions/${versionId}/credential`);
  }

  /**
   * 测试Jira连接
   */
  async testJiraConnection(versionId: number) {
    return this.get<any>(`/api/versions/${versionId}/jira-test`);
  }

  /**
   * 同步Jira数据
   */
  async syncJiraData(versionId: number, data: any, stage: string = "STR1") {
    return this.post<any>(`/api/versions/${versionId}/sync`, data, { stage });
  }

  /**
   * 获取同步进度
   */
  async getSyncProgress() {
    return this.get<any>("/api/sync-progress");
  }

  /**
   * 获取全局Jira凭据
   */
  async getGlobalCredential() {
    return this.get<any>("/api/jira/global-credential");
  }

  /**
   * 设置全局Jira凭据
   */
  async setGlobalCredential(username: string, password: string, baseUrl?: string) {
    return this.post<any>("/api/jira/global-credential", undefined, {
      username,
      password,
      base_url: baseUrl || "http://jira.transsion.com",
    });
  }

  /**
   * 获取Jira问题列表
   */
  async getJiraIssues(versionId: number, filterKey: string, stage: string = "STR1") {
    return this.get<any>(`/api/versions/${versionId}/jira-issues/${filterKey}`, { stage });
  }

  /**
   * 获取过滤器列表
   */
  async getFilters(versionId: number) {
    return this.get<any[]>(`/api/versions/${versionId}/filters`);
  }

  /**
   * 更新过滤器
   */
  async updateFilter(versionId: number, filterKey: string, data: any) {
    return this.put<any>(`/api/versions/${versionId}/filters/${filterKey}`, data);
  }

  /**
   * 重置过滤器
   */
  async resetFilter(versionId: number, filterKey: string) {
    return this.post<any>(`/api/versions/${versionId}/filters/${filterKey}/reset`);
  }

  /**
   * 获取JQL
   */
  async getJql(versionId: number, filterKey: string) {
    return this.get<any>(`/api/versions/${versionId}/jql/${filterKey}`);
  }

  /**
   * 获取待验证问题数量
   */
  async getPendingVerificationCount(versionId: number, stage: string = "STR1") {
    return this.get<any>(`/api/versions/${versionId}/pending-verification-count`, { stage });
  }

  // ==================== 分析相关 ====================

  /**
   * 获取分析报告
   */
  async getAnalysis(versionId: number, stage: string = "STR1") {
    return this.get<any>(`/api/versions/${versionId}/analysis`, { stage });
  }

  /**
   * 获取趋势数据
   */
  async getTrends(versionId: number, stage: string = "ALL") {
    return this.get<any>(`/api/versions/${versionId}/trends`, { stage });
  }

  // ==================== 飞书相关 ====================

  /**
   * 获取飞书配置
   */
  async getFeishuConfig() {
    return this.get<any>("/api/feishu/config");
  }

  /**
   * 保存飞书配置
   */
  async saveFeishuConfig(data: any) {
    return this.post<any>("/api/feishu/config", data);
  }

  /**
   * 飞书登录
   */
  async feishuLogin() {
    return this.get<any>("/api/feishu/login");
  }

  /**
   * 获取飞书Token状态
   */
  async getFeishuTokenStatus() {
    return this.get<any>("/api/feishu/token-status");
  }

  /**
   * 导入飞书阶段
   */
  async importFeishuStages(versionId: number, data: any) {
    return this.post<any>(`/api/versions/${versionId}/stages/import-feishu`, data);
  }

  // ==================== ALM 相关 ====================

  /**
   * 获取ALM配置
   */
  async getALMConfig() {
    return this.get<any>("/api/alm/config");
  }

  /**
   * 保存ALM配置
   */
  async saveALMConfig(data: any) {
    return this.post<any>("/api/alm/config", data);
  }

  // ==================== AI 相关 ====================

  /**
   * 获取AI配置
   */
  async getAIConfig() {
    return this.get<any>("/api/ai/config");
  }

  /**
   * 保存AI配置
   */
  async saveAIConfig(data: any) {
    return this.post<any>("/api/ai/config", data);
  }

  /**
   * AI质量总结
   */
  async aiQualitySummary(versionId: number, stage: string = "ALL") {
    return this.post<any>(`/api/versions/${versionId}/ai/summary`, undefined, { stage });
  }

  /**
   * AI风险分析
   */
  async aiRiskAnalysis(versionId: number, stage: string = "ALL") {
    return this.post<any>(`/api/versions/${versionId}/ai/risk`, undefined, { stage });
  }

  /**
   * AI周报
   */
  async aiWeeklyReport(versionId: number, stage: string = "ALL") {
    return this.post<any>(`/api/versions/${versionId}/ai/weekly`, undefined, { stage });
  }

  // ==================== 稳定性相关 ====================

  /**
   * 获取稳定性数据
   */
  async getStabilityData(versionId: number) {
    return this.get<any>(`/api/versions/${versionId}/stability`);
  }

  /**
   * 保存稳定性数据
   */
  async saveStabilityData(versionId: number, data: any) {
    return this.post<any>(`/api/versions/${versionId}/stability`, data);
  }

  /**
   * 初始化稳定性设备
   */
  async initStabilityDevices(versionId: number, deviceNames?: string[]) {
    return this.post<any>(`/api/versions/${versionId}/stability/init`, deviceNames);
  }

  /**
   * 删除稳定性设备
   */
  async deleteStabilityDevice(versionId: number, deviceName: string) {
    return this.delete<any>(`/api/versions/${versionId}/stability/${deviceName}`);
  }

  // ==================== 性能相关 ====================

  /**
   * 获取性能数据
   */
  async getPerformanceData(versionId: number) {
    return this.get<any>(`/api/versions/${versionId}/performance`);
  }

  // ==================== 续航相关 ====================

  /**
   * 获取续航数据
   */
  async getBatteryData(versionId: number) {
    return this.get<any>(`/api/versions/${versionId}/battery`);
  }

  // ==================== SR 相关 ====================

  /**
   * 获取SR需求详情缓存
   */
  async getSRDetailCached(versionId: number) {
    return this.get<any>(`/api/versions/${versionId}/sr-detail-cached`);
  }

  /**
   * 刷新SR需求详情
   */
  async refreshSRDetails(versionId: number) {
    return this.post<any>(`/api/versions/${versionId}/sr-detail-refresh`);
  }

  /**
   * 获取SR需求详情
   */
  async getSRDetails(versionId: number) {
    return this.get<any>(`/api/versions/${versionId}/sr-details`);
  }

  /**
   * 获取SR遗留问题缓存
   */
  async getSRIssuesCached(versionId: number) {
    return this.get<any>(`/api/versions/${versionId}/sr-issues-cached`);
  }

  /**
   * 刷新SR遗留问题
   */
  async refreshSRIssues(versionId: number) {
    return this.post<any>(`/api/versions/${versionId}/sr-issues-refresh`);
  }

  /**
   * 获取SR AI分析结果
   */
  async getSRAIAnalysis(versionId: number) {
    return this.get<any>(`/api/versions/${versionId}/sr-ai-analysis`);
  }

  /**
   * 删除SR AI分析结果
   */
  async deleteSRAIAnalysis(versionId: number, srCodings: string[]) {
    return this.delete<any>(`/api/versions/${versionId}/sr-ai-analysis`, {
      sr_coding: srCodings.join(","),
    });
  }

  /**
   * 运行SR AI分析
   */
  async runSRAIAnalysis(versionId: number, srCodings: string[]) {
    return this.post<any>(`/api/versions/${versionId}/sr-ai-analysis`, undefined, {
      sr_coding: srCodings.join(","),
    });
  }

  /**
   * 获取SR AI风险等级
   */
  async getSRAIPriority(versionId: number) {
    return this.get<any>(`/api/versions/${versionId}/sr-ai-priority`);
  }

  /**
   * 运行SR AI风险等级分析
   */
  async runSRAIPriority(versionId: number, force: boolean = false) {
    return this.post<any>(`/api/versions/${versionId}/sr-ai-priority`, undefined, {
      force: force.toString(),
    });
  }

  /**
   * 获取SR每日风险报告
   */
  async getSRDailyRiskReport(versionId: number) {
    return this.get<any>(`/api/versions/${versionId}/sr-daily-risk-report`);
  }

  /**
   * 获取今日SR风险报告
   */
  async getSRDailyRiskReportToday(versionId: number) {
    return this.get<any>(`/api/versions/${versionId}/sr-daily-risk-report/today`);
  }

  // ==================== 测试计划相关 ====================

  /**
   * 获取测试计划
   */
  async getTestPlans(versionId: number, planType: string) {
    return this.get<any>(`/api/versions/${versionId}/test-plans/${planType}`);
  }

  /**
   * 保存测试计划
   */
  async saveTestPlan(versionId: number, planType: string, data: any) {
    return this.post<any>(`/api/versions/${versionId}/test-plans/${planType}`, data);
  }

  /**
   * 删除测试计划
   */
  async deleteTestPlan(versionId: number, planType: string, deviceName: string) {
    return this.delete<any>(`/api/versions/${versionId}/test-plans/${planType}/${deviceName}`);
  }

  // ==================== 价值点相关 ====================

  /**
   * 获取价值点
   */
  async getValuePoints(versionId: number) {
    return this.get<any>(`/api/versions/${versionId}/value-points`);
  }

  /**
   * 保存价值点
   */
  async saveValuePoint(versionId: number, data: any) {
    return this.post<any>(`/api/versions/${versionId}/value-points`, data);
  }

  /**
   * 删除价值点
   */
  async deleteValuePoint(versionId: number, valueId: number) {
    return this.delete<any>(`/api/versions/${versionId}/value-points/${valueId}`);
  }

  // ==================== 报告相关 ====================

  /**
   * 获取报告列表
   */
  async getReports() {
    return this.get<any>("/api/output/reports");
  }

  /**
   * 获取报告内容
   */
  async getReport(filename: string) {
    return this.get<any>(`/api/output/reports/${filename}`);
  }

  // ==================== 管理相关 ====================

  /**
   * 健康检查
   */
  async healthCheck() {
    return this.get<any>("/api/health");
  }

  /**
   * 获取默认配置
   */
  async getConfigDefaults() {
    return this.get<any>("/api/config/defaults");
  }

  /**
   * 重置数据库
   */
  async resetDatabase() {
    return this.post<any>("/api/admin/reset-db");
  }

  /**
   * 清空缓存
   */
  async clearCache() {
    return this.post<any>("/api/admin/clear-cache");
  }
}

// 导出单例
export const apiClient = new ApiClient();
export default apiClient;