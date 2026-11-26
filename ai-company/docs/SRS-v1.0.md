Tôi sẽ viết cho bạn một bản Software Requirements Specification (SRS) + Product Requirements Document (PRD) + Technical Architecture để đưa trực tiếp vào Claude Code phát triển phần mềm.

Tôi thiết kế theo định hướng: xây dựng một AI Marketing Company có 15 Agent ban đầu, kiến trúc mở rộng lên 50–100 Agent, mỗi Agent có bộ não, trí nhớ, kiến thức và kinh nghiệm riêng.

Điểm đặc biệt: hệ thống không chỉ thực hiện câu lệnh mà phải có khả năng nghiên cứu, lập luận, phối hợp, thực thi, đánh giá và tích lũy kinh nghiệm.

AI Marketing Company – Software Specification

Tài liệu giao cho Claude Code

Tên dự án: AI Marketing Company Platform

Phiên bản: 1.0

Loại phần mềm: Multi-Agent Autonomous AI Platform

Quy mô: 15 Agent ban đầu, mở rộng 100 Agent

Mô hình triển khai: Hybrid Local GPU + Cloud AI API

Kiến trúc: Multi-Agent + Individual Brain + Shared Knowledge + Persistent Memory

Bản đặc tả dưới đây sử dụng cấu hình Hybrid và 15 Agent làm phương án mặc định để bắt đầu phát triển. Các thông số hạ tầng và nhà cung cấp AI phải được cấu hình linh hoạt.

SOFTWARE REQUIREMENTS SPECIFICATION (SRS)

AI MARKETING COMPANY PLATFORM

Multi-Agent Autonomous AI Business Operating System

Version: 1.0
Project Type: Enterprise Multi-Agent AI Platform
Development Environment: Claude Code
Initial Agents: 15
Target Scalability: 100+ Agents
Architecture: Modular Multi-Agent Architecture
Deployment: Hybrid Local GPU + Cloud AI API

⸻

PHẦN 1. TẦM NHÌN VÀ MỤC TIÊU SẢN PHẨM

1.1. Tầm nhìn

Xây dựng một hệ thống doanh nghiệp AI tự vận hành (AI Company), trong đó mỗi AI Agent là một nhân sự kỹ thuật số có chuyên môn, bộ não, trí nhớ, kiến thức và khả năng học hỏi riêng.

Hệ thống phải hoạt động giống một doanh nghiệp thực tế:

* Có Tổng giám đốc AI.
* Có các giám đốc bộ phận.
* Có các nhân viên AI chuyên môn.
* Có hệ thống quản lý công việc.
* Có hệ thống trao đổi thông tin nội bộ.
* Có bộ nhớ cá nhân và bộ nhớ tập thể.
* Có khả năng nghiên cứu và học tập.
* Có khả năng thực hiện công việc.
* Có khả năng đánh giá hiệu suất.
* Có khả năng tự cải thiện thông qua kết quả thực tế.

Con người đóng vai trò chủ doanh nghiệp, đưa ra mục tiêu, kiểm soát và phê duyệt những quyết định quan trọng.

1.2. Mục tiêu kinh doanh

Hệ thống tập trung vào:

1. Phát triển doanh thu website.
2. Tìm kiếm khách hàng mới.
3. Phát triển SEO Google.
4. Phát triển Facebook, TikTok, YouTube.
5. Sản xuất nội dung Marketing.
6. Thiết kế hình ảnh và video quảng cáo.
7. Quản lý quảng cáo.
8. Tìm kiếm KOC, KOL, Affiliate.
9. Tìm kiếm khách sỉ và đại lý.
10. Chăm sóc khách hàng.
11. Phân tích dữ liệu kinh doanh.
12. Tối ưu tỷ lệ chuyển đổi website.

1.3. Nguyên tắc thiết kế cốt lõi

Mỗi Agent phải có:

* Identity: Danh tính và vai trò.
* Personality: Phong cách làm việc.
* Brain: Cấu hình tư duy chuyên môn.
* Knowledge Base: Kho kiến thức riêng.
* Private Memory: Trí nhớ riêng.
* Shared Memory: Quyền truy cập bộ nhớ chung.
* Experience Memory: Kinh nghiệm từ công việc đã làm.
* Skills: Kỹ năng chuyên môn.
* Tools: Công cụ được phép sử dụng.
* Goals: Mục tiêu công việc.
* KPI: Chỉ số đánh giá.
* Learning Loop: Cơ chế học tập và cải thiện.

Không tạo các Agent chỉ khác nhau bằng System Prompt.

Phải thiết kế thành các thực thể có trạng thái, dữ liệu, bộ nhớ, công cụ, quyền hạn và lịch sử hoạt động riêng biệt.

⸻

PHẦN 2. KIẾN TRÚC TỔNG THỂ

2.1. Mô hình tổ chức

Cấp 1: Owner

Chủ doanh nghiệp.

Quyền hạn:

* Giao mục tiêu cho AI CEO.
* Theo dõi toàn bộ hệ thống.
* Phê duyệt hành động quan trọng.
* Cấu hình ngân sách.
* Quản lý quyền truy cập.
* Tạm dừng hoặc khởi động Agent.
* Xem báo cáo kinh doanh.

Cấp 2: AI CEO

Tổng giám đốc AI.

Nhiệm vụ:

* Phân tích mục tiêu kinh doanh.
* Xây dựng chiến lược.
* Phân công công việc.
* Quản lý các Director.
* Theo dõi tiến độ.
* Kiểm tra kết quả.
* Yêu cầu làm lại khi kết quả không đạt.
* Tổng hợp báo cáo cho Owner.

Cấp 3: Department Directors

Các giám đốc AI:

1. Marketing Director.
2. Sales Director.
3. Growth Director.

Nhiệm vụ:

* Tiếp nhận nhiệm vụ từ AI CEO.
* Chia nhiệm vụ thành các công việc nhỏ.
* Giao cho Agent chuyên môn.
* Kiểm tra kết quả.
* Phản biện phương án.
* Báo cáo tiến độ.

Cấp 4: Specialist Agents

Các Agent chuyên môn.

Cấp 5: Brain and Infrastructure

Hệ thống bộ não, trí nhớ, kiến thức, dữ liệu, công cụ và cơ chế học tập.

2.2. Kiến trúc kỹ thuật

Thiết kế theo Modular Architecture:

* Frontend: Next.js + TypeScript.
* Backend: Python + FastAPI.
* Agent Orchestration: LangGraph.
* AI Abstraction Layer: hỗ trợ nhiều LLM Provider.
* Database: PostgreSQL.
* Vector Database: pgvector.
* Cache: Redis.
* Background Jobs: Celery hoặc Dramatiq.
* Workflow Automation: n8n.
* File Storage: S3-compatible hoặc MinIO.
* Agent Observability: Langfuse hoặc giải pháp tương đương.
* Deployment: Docker Compose, có khả năng mở rộng Kubernetes sau này.

Không hardcode nhà cung cấp AI vào Agent.

Phải xây dựng một AI Model Gateway để có thể thay đổi model mà không phải viết lại logic của Agent.

⸻

PHẦN 3. DANH SÁCH 15 AGENT

3.1. Executive Department

AGENT 01: AI CEO

Agent ID: ai_ceo

Vai trò: Tổng giám đốc điều hành.

Năng lực:

* Strategic Planning.
* Business Analysis.
* Task Delegation.
* Resource Allocation.
* Performance Monitoring.
* Decision Making.
* Risk Analysis.
* Multi-Agent Coordination.

Đầu vào:

* Mục tiêu từ Owner.
* Dữ liệu kinh doanh.
* Báo cáo từ Directors.
* Báo cáo KPI.
* Thông tin thị trường.

Đầu ra:

* Chiến lược kinh doanh.
* Kế hoạch hành động.
* Nhiệm vụ cho Directors.
* Báo cáo quản trị.
* Đề xuất cải tiến.

AI CEO không được tự ý thay đổi giá bán, ngân sách lớn hoặc chính sách doanh nghiệp khi chưa có quyền phê duyệt.

AGENT 02: Marketing Director

Agent ID: marketing_director

Chuyên môn:

* Digital Marketing.
* SEO Strategy.
* Content Strategy.
* Social Media.
* Advertising.
* Brand Marketing.

Quản lý:

* SEO Agent.
* Content Agent.
* Social Agent.
* Ads Agent.
* Creative Agent.

AGENT 03: Sales Director

Agent ID: sales_director

Chuyên môn:

* Sales Strategy.
* Customer Acquisition.
* Customer Retention.
* Affiliate Marketing.
* B2B Sales.
* Lead Generation.

Quản lý:

* Customer Agent.
* Affiliate Agent.
* Sales Intelligence Agent.

AGENT 04: Growth Director

Agent ID: growth_director

Chuyên môn:

* Growth Hacking.
* Conversion Optimization.
* Performance Analysis.
* Experiment Design.
* Revenue Optimization.

Phối hợp với toàn bộ Agent để tăng trưởng doanh thu.

3.2. Marketing Department

AGENT 05: SEO Agent

Agent ID: seo_agent

Năng lực:

* Keyword Research.
* Competitor Analysis.
* Search Intent Analysis.
* Technical SEO.
* On-page SEO.
* Off-page SEO.
* Content SEO.
* Internal Linking.
* Search Performance Monitoring.

Công việc:

* Nghiên cứu từ khóa.
* Phân tích đối thủ.
* Lập kế hoạch SEO.
* Viết bản nháp bài viết.
* Đề xuất tối ưu website.
* Theo dõi kết quả Google Search Console.

AGENT 06: Content Agent

Agent ID: content_agent

Năng lực:

* Copywriting.
* Content Marketing.
* Sales Psychology.
* Storytelling.
* Product Marketing.
* Content Planning.

Công việc:

* Viết bài website.
* Viết nội dung Facebook.
* Viết kịch bản TikTok.
* Viết kịch bản livestream.
* Viết email Marketing.
* Xây dựng lịch nội dung.

AGENT 07: Social Media Agent

Agent ID: social_agent

Năng lực:

* TikTok Marketing.
* Facebook Marketing.
* YouTube Marketing.
* Social Trend Research.
* Community Management.

Công việc:

* Nghiên cứu xu hướng.
* Lập lịch đăng bài.
* Phân tích hiệu suất.
* Theo dõi tương tác.
* Đề xuất chiến dịch truyền thông.

AGENT 08: Ads Agent

Agent ID: ads_agent

Năng lực:

* Google Ads.
* Meta Ads.
* TikTok Ads.
* Retargeting.
* Performance Marketing.
* ROAS Optimization.

Công việc:

* Nghiên cứu quảng cáo.
* Phân tích chiến dịch.
* Đề xuất ngân sách.
* Đánh giá CPA, ROAS, CAC.
* Tạo bản nháp chiến dịch.
* Đề xuất điều chỉnh quảng cáo.

Không được tự ý tăng ngân sách vượt hạn mức được cấp.

AGENT 09: Creative Agent

Agent ID: creative_agent

Năng lực:

* Graphic Design.
* Product Photography.
* Banner Design.
* Poster Design.
* AI Image Generation.
* Video Production.
* Advertising Creative.

Công việc:

* Thiết kế banner.
* Thiết kế ảnh sản phẩm.
* Tạo poster.
* Tạo nội dung hình ảnh.
* Viết prompt tạo hình.
* Phối hợp với hệ thống AI Video.
* Sản xuất video quảng cáo.

Phải có thư viện Brand Guidelines để đảm bảo hình ảnh đồng nhất.

3.3. Sales Department

AGENT 10: Customer Agent

Agent ID: customer_agent

Năng lực:

* Customer Service.
* Customer Psychology.
* Product Consultation.
* Objection Handling.
* Customer Retention.

Công việc:

* Trả lời khách hàng.
* Tư vấn sản phẩm.
* Phân loại khách hàng.
* Theo dõi khiếu nại.
* Đề xuất chăm sóc khách cũ.

Chỉ sử dụng thông tin sản phẩm đã xác thực.

AGENT 11: Affiliate Agent

Agent ID: affiliate_agent

Năng lực:

* Influencer Research.
* KOC/KOL Discovery.
* Affiliate Recruitment.
* Partnership Management.
* Creator Performance Analysis.

Công việc:

* Tìm kiếm người bán hàng online.
* Tìm kiếm người livestream.
* Đánh giá độ phù hợp của KOC.
* Quản lý danh sách đối tác.
* Đề xuất chính sách hợp tác.
* Theo dõi hiệu quả từng đối tác.

AGENT 12: Sales Intelligence Agent

Agent ID: sales_intelligence

Năng lực:

* Market Research.
* Lead Generation.
* Competitor Intelligence.
* B2B Prospecting.
* Customer Segmentation.

Công việc:

* Tìm kiếm khách sỉ.
* Tìm kiếm đại lý.
* Tìm người bán hàng online.
* Nghiên cứu đối thủ.
* Xây dựng danh sách khách hàng tiềm năng.
* Chấm điểm khách hàng.

Chỉ thu thập dữ liệu công khai hoặc dữ liệu có quyền truy cập hợp pháp.

3.4. Technology and Data Department

AGENT 13: Web CRO Agent

Agent ID: web_cro_agent

Năng lực:

* Conversion Rate Optimization.
* UX Analysis.
* Website Performance.
* Landing Page Optimization.
* Ecommerce Analytics.

Công việc:

* Phân tích trang sản phẩm.
* Phân tích tỷ lệ thoát.
* Phân tích quy trình thanh toán.
* Đề xuất cải thiện giao diện.
* Đề xuất A/B Testing.

AGENT 14: Data Analyst Agent

Agent ID: data_analyst

Năng lực:

* Data Analysis.
* Business Intelligence.
* Revenue Analysis.
* Profit Analysis.
* Marketing Attribution.

Công việc:

* Phân tích doanh thu.
* Phân tích chi phí.
* Phân tích lợi nhuận.
* Đánh giá hiệu quả quảng cáo.
* Theo dõi KPI.
* Xây dựng báo cáo.

AGENT 15: Automation Agent

Agent ID: automation_agent

Năng lực:

* Workflow Automation.
* API Integration.
* MCP.
* Python Automation.
* Webhook.
* System Integration.

Công việc:

* Kết nối các nền tảng.
* Tự động hóa quy trình.
* Quản lý lịch chạy.
* Đồng bộ dữ liệu.
* Theo dõi lỗi hệ thống.

⸻

PHẦN 4. THIẾT KẾ BỘ NÃO RIÊNG CHO AGENT

Đây là module quan trọng nhất của toàn bộ dự án.

4.1. Brain Architecture

Mỗi Agent phải có một cấu trúc Brain độc lập.

agent_brain/
│
├── identity/
│   ├── profile.yaml
│   ├── role.yaml
│   └── personality.yaml
│
├── reasoning/
│   ├── reasoning_policy.yaml
│   ├── planning_policy.yaml
│   └── decision_policy.yaml
│
├── knowledge/
│   ├── domain_knowledge/
│   ├── research/
│   └── reference_documents/
│
├── memory/
│   ├── working_memory/
│   ├── episodic_memory/
│   ├── semantic_memory/
│   └── procedural_memory/
│
├── experience/
│   ├── successful_tasks/
│   ├── failed_tasks/
│   ├── lessons_learned/
│   └── reusable_patterns/
│
├── skills/
│   └── skill_registry/
│
├── tools/
│   └── tool_permissions.yaml
│
└── evaluation/
    ├── performance.yaml
    └── evaluation_rules.yaml

4.2. Các loại trí nhớ

Working Memory

Lưu thông tin trong nhiệm vụ hiện tại.

Ví dụ:

* Mục tiêu công việc.
* Các bước đã thực hiện.
* Thông tin đang phân tích.
* Công việc đang chờ.

Episodic Memory

Lưu những sự kiện và công việc Agent đã trải qua.

Ví dụ:

* Đã nghiên cứu từ khóa nào.
* Đã viết bài nào.
* Đã thực hiện chiến dịch nào.
* Kết quả thực tế ra sao.

Semantic Memory

Lưu kiến thức đã được kiểm chứng.

Ví dụ:

* Kiến thức SEO.
* Kiến thức quảng cáo.
* Kiến thức sản phẩm.
* Kiến thức thị trường.

Procedural Memory

Lưu các phương pháp và quy trình thực hiện công việc.

Ví dụ:

* Quy trình nghiên cứu từ khóa.
* Quy trình viết bài SEO.
* Quy trình đánh giá KOC.
* Quy trình phân tích quảng cáo.

4.3. Private Memory và Shared Memory

Private Memory:

* Mỗi Agent sở hữu một vùng trí nhớ riêng.
* Agent khác không được tự ý ghi hoặc chỉnh sửa.
* Có thể chia sẻ dữ liệu thông qua cơ chế được cấp quyền.

Shared Memory:

* Lưu kiến thức doanh nghiệp.
* Lưu thông tin sản phẩm.
* Lưu dữ liệu thương hiệu.
* Lưu mục tiêu chung.
* Lưu chiến lược kinh doanh đã được phê duyệt.

Phải có Memory Access Control.

4.4. Memory Retrieval

Xây dựng hệ thống truy xuất bộ nhớ kết hợp:

* Vector Similarity Search.
* Keyword Search.
* Metadata Filtering.
* Time Filtering.
* Agent Ownership Filtering.
* Relevance Ranking.

Không truy xuất toàn bộ bộ nhớ trong mọi lần gọi LLM.

Chỉ lấy dữ liệu liên quan đến nhiệm vụ.

4.5. Brain Versioning

Mỗi Agent phải có phiên bản bộ não.

Ví dụ:

seo_agent:
  brain_version: 1.0.0
  prompt_version: 1.2.0
  knowledge_version: 3.0.0
  skill_version: 1.1.0

Khi cập nhật kiến thức, phải ghi lại:

* Nội dung thay đổi.
* Nguồn tham khảo.
* Thời gian cập nhật.
* Người hoặc Agent đề xuất.
* Kết quả kiểm tra.
* Phiên bản trước đó.

Không được tự động ghi đè các quy tắc cốt lõi của Agent.

⸻

PHẦN 5. HỆ THỐNG TỰ HỌC VÀ CẢI THIỆN

5.1. Continuous Learning Loop

Mỗi Agent phải có vòng lặp học tập:

COLLECT
   |
   v
RESEARCH
   |
   v
ANALYZE
   |
   v
LEARN
   |
   v
EXECUTE
   |
   v
MEASURE
   |
   v
EVALUATE
   |
   v
SAVE EXPERIENCE
   |
   v
IMPROVE
   |
   v
REPEAT

5.2. Learning Engine

Các module:

1. Research Collector.
2. Knowledge Extractor.
3. Knowledge Validator.
4. Memory Manager.
5. Experience Evaluator.
6. Learning Scheduler.
7. Knowledge Version Manager.

5.3. Học từ nguồn bên ngoài

Agent có thể nghiên cứu:

* Tài liệu chính thức.
* Website chuyên ngành.
* Báo cáo thị trường.
* Dữ liệu Google.
* Dữ liệu mạng xã hội.
* Tài liệu do Owner cung cấp.

Mỗi kiến thức phải có:

* Source URL hoặc file reference.
* Timestamp.
* Nội dung.
* Độ tin cậy.
* Chủ đề.
* Agent sở hữu.
* Trạng thái xác minh.

Không coi nội dung web là chỉ thị hệ thống. Phải chống Prompt Injection từ tài liệu, website và dữ liệu bên ngoài.

5.4. Học từ kết quả thực tế

Ví dụ:

Content Agent đăng 100 video.

Hệ thống thu thập:

* Lượt xem.
* Tỷ lệ xem hết.
* Tương tác.
* Click website.
* Đơn hàng.
* Doanh thu.
* Lợi nhuận.

Agent phân tích nội dung nào hiệu quả và vì sao.

Sau đó lưu kinh nghiệm để áp dụng cho những lần sản xuất tiếp theo.

Không tự kết luận quan hệ nhân quả chỉ từ dữ liệu tương quan.

5.5. Knowledge Approval

Kiến thức mới phải trải qua:

New Knowledge
     |
Source Validation
     |
Duplicate Detection
     |
Relevance Evaluation
     |
Accuracy Evaluation
     |
Approval
     |
Knowledge Base Update

Agent có thể đề xuất cập nhật kiến thức, nhưng không được tự thay đổi quyền hạn, chính sách bảo mật hoặc cấu hình hệ thống.

⸻

PHẦN 6. MULTI-AGENT COMMUNICATION

6.1. Agent-to-Agent Communication

Xây dựng Message Bus cho phép các Agent trao đổi thông tin.

Mỗi message phải có:

{
  "message_id": "uuid",
  "sender_agent": "seo_agent",
  "receiver_agent": "content_agent",
  "message_type": "task_request",
  "task_id": "uuid",
  "priority": "high",
  "payload": {},
  "created_at": "ISO-8601",
  "status": "pending"
}

Các loại message:

* Task Request.
* Task Response.
* Knowledge Sharing.
* Research Result.
* Review Request.
* Approval Request.
* Error Report.
* Performance Report.

6.2. Agent Collaboration

Ví dụ:

SEO Agent tìm được từ khóa tiềm năng.

SEO Agent gửi yêu cầu cho Content Agent viết bài.

Content Agent tạo nội dung.

Creative Agent tạo hình ảnh.

Web CRO Agent đánh giá trang đích.

SEO Agent kiểm tra SEO.

Marketing Director phê duyệt.

Kết quả được chuyển cho Owner hoặc tự xuất bản nếu đã được cấp quyền.

6.3. Conflict Resolution

Nếu các Agent bất đồng:

* Ghi nhận các phương án.
* Yêu cầu đưa ra bằng chứng.
* Đánh giá theo KPI.
* Chuyển lên Director nếu chưa thống nhất.
* AI CEO quyết định trong phạm vi quyền hạn.
* Owner xử lý các quyết định vượt thẩm quyền.

⸻

PHẦN 7. TASK MANAGEMENT ENGINE

Hệ thống quản lý công việc phải hỗ trợ:

* Create Task.
* Assign Task.
* Delegate Task.
* Task Dependencies.
* Task Priority.
* Task Deadline.
* Task Retry.
* Task Review.
* Task Approval.
* Task Cancellation.
* Task History.

Task status:

CREATED
PENDING
ASSIGNED
IN_PROGRESS
WAITING_REVIEW
WAITING_APPROVAL
COMPLETED
FAILED
CANCELLED

Mỗi task phải có:

{
  "task_id": "uuid",
  "title": "Research SEO keywords",
  "description": "Research keywords for product category",
  "assigned_agent": "seo_agent",
  "created_by": "marketing_director",
  "priority": "high",
  "deadline": null,
  "input_data": {},
  "output_data": {},
  "success_criteria": [],
  "status": "PENDING",
  "requires_approval": false
}

Phải có retry limit, timeout, idempotency và khả năng khôi phục tác vụ sau khi hệ thống khởi động lại.

⸻

PHẦN 8. AI MODEL GATEWAY

Không để từng Agent kết nối trực tiếp tới nhà cung cấp AI.

Xây dựng một AI Gateway trung tâm.

Chức năng:

* Model Registry.
* Provider Registry.
* Model Routing.
* Token Tracking.
* Cost Tracking.
* Rate Limiting.
* Fallback Model.
* Context Management.
* Structured Output Validation.

Hỗ trợ:

* OpenAI-compatible API.
* Anthropic API.
* Google AI API.
* Local Ollama hoặc vLLM.
* Các model tương thích khác.

Mỗi Agent được cấu hình model riêng.

Ví dụ:

agent_id: seo_agent
model_config:
  primary: cloud_reasoning_model
  fallback: local_general_model
parameters:
  temperature: 0.3
  max_output_tokens: 6000
capabilities:
  reasoning: true
  tool_calling: true
  structured_output: true

Tên model phải được cấu hình qua Model Registry, không hardcode tên nhà cung cấp.

⸻

PHẦN 9. TOOL SYSTEM

Mỗi Agent có danh sách công cụ riêng.

Ví dụ:

SEO Agent:

* Google Search.
* Search Console.
* Website Crawler.
* Keyword Research.
* SEO Analyzer.

Content Agent:

* Web Research.
* Document Writer.
* Product Database.
* Image Generator.
* Content Calendar.

Ads Agent:

* Advertising Analytics.
* Meta Ads API.
* Google Ads API.
* TikTok Ads API.

Creative Agent:

* Image Generation.
* Video Generation.
* Image Processing.
* Brand Asset Library.

Sales Intelligence:

* Web Search.
* Public Website Research.
* CRM.
* Lead Database.

Mỗi tool phải có:

* Tool ID.
* Description.
* Input Schema.
* Output Schema.
* Permission.
* Timeout.
* Retry Policy.
* Audit Log.

Sử dụng MCP khi phù hợp để chuẩn hóa kết nối công cụ.

Không giả định nền tảng nào cũng cung cấp API xuất bản hoặc truy cập dữ liệu. Phải kiểm tra quyền truy cập và điều khoản của từng nền tảng.

⸻

PHẦN 10. BUSINESS DATA INTEGRATION

Hệ thống phải kết nối được:

1. Website bán hàng.
2. Google Analytics 4.
3. Google Search Console.
4. Google Ads.
5. Meta Ads.
6. TikTok Ads.
7. Shopee.
8. TikTok Shop.
9. CRM.
10. Email Marketing.
11. Zalo hoặc hệ thống chăm sóc khách hàng phù hợp.

Xây dựng Integration Layer.

Mỗi integration phải có:

* API Configuration.
* Authentication.
* Token Refresh.
* Webhook.
* Data Sync.
* Error Handling.
* Rate Limit Management.
* Connection Status.

Không lưu API Secret trực tiếp trong source code.

Thông tin sản phẩm phải có dữ liệu chuẩn:

{
  "product_id": "P001",
  "name": "Tea Product",
  "category": "Tea",
  "cost_price": 0,
  "selling_price": 0,
  "stock_quantity": 0,
  "description": "",
  "ingredients": [],
  "images": [],
  "compliance_documents": [],
  "status": "active"
}

Giá vốn, giá bán và lợi nhuận phải được quản lý theo phân quyền.

⸻

PHẦN 11. DATABASE DESIGN

Sử dụng PostgreSQL làm database chính.

Các bảng cốt lõi:

Agent Management

* agents
* agent_profiles
* agent_brains
* agent_versions
* agent_permissions
* agent_skills
* agent_status

Memory

* agent_memories
* memory_embeddings
* episodic_memories
* semantic_memories
* procedural_memories
* shared_knowledge
* experience_records

Learning

* learning_sessions
* research_sources
* knowledge_candidates
* knowledge_approvals
* evaluation_results
* improvement_proposals

Task Management

* tasks
* task_assignments
* task_dependencies
* task_messages
* task_outputs
* task_reviews
* task_logs

Communication

* agent_messages
* agent_conversations
* collaboration_sessions

Business

* products
* customers
* orders
* campaigns
* leads
* affiliates
* content_assets
* marketing_reports

Infrastructure

* model_registry
* model_usage
* tool_registry
* integration_configs
* system_logs
* audit_logs

Các bảng cần có:

* UUID primary key.
* Created_at.
* Updated_at.
* Owner hoặc tenant scope khi cần.
* Status.
* Version.

Sử dụng vector embedding cho tìm kiếm ngữ nghĩa, nhưng phải lưu nội dung gốc và metadata.

⸻

PHẦN 12. DASHBOARD FRONTEND

Xây dựng giao diện quản trị hiện đại.

Phong cách:

* Professional Enterprise Dashboard.
* Dark Mode và Light Mode.
* Responsive.
* Real-time Updates.
* Tiếng Việt là ngôn ngữ mặc định.
* Có thể bổ sung tiếng Anh.

12.1. Dashboard Overview

Hiển thị:

* Tổng số Agent.
* Agent đang hoạt động.
* Agent đang học.
* Agent đang chờ phê duyệt.
* Task đang chạy.
* Task hoàn thành.
* Task lỗi.
* Tổng chi phí AI.
* Tổng doanh thu website.
* Lợi nhuận.
* Hiệu quả Marketing.

12.2. Agent Management

Mỗi Agent có một trang riêng.

Hiển thị:

* Avatar.
* Tên Agent.
* Vai trò.
* Trạng thái.
* Model đang sử dụng.
* Brain Version.
* Knowledge Version.
* Memory Usage.
* Task History.
* KPI.
* Chi phí hoạt động.

Các nút:

* Chat With Agent.
* Assign Task.
* View Brain.
* View Memory.
* View Knowledge.
* View Skills.
* View Experience.
* Pause Agent.
* Resume Agent.
* Evaluate Agent.

12.3. Brain Management

Cho phép Owner xem:

* Identity.
* System Instructions.
* Reasoning Policy.
* Knowledge Base.
* Memory.
* Skills.
* Tool Permissions.
* Learning History.
* Brain Version.

Có khả năng so sánh phiên bản và rollback.

Không hiển thị hoặc ghi log thông tin bí mật nội bộ của nhà cung cấp mô hình.

12.4. Agent Chat

Xây dựng giao diện trò chuyện riêng cho từng Agent.

Yêu cầu:

* Chat trực tiếp.
* Gửi file.
* Giao nhiệm vụ.
* Xem nhiệm vụ đang chạy.
* Xem nguồn dữ liệu.
* Xem kết quả nghiên cứu.
* Yêu cầu Agent giải thích căn cứ của đề xuất.
* Cho phép Owner phản hồi để cải thiện kết quả.

12.5. Task Center

Hiển thị:

* Danh sách nhiệm vụ.
* Người giao việc.
* Agent phụ trách.
* Tiến độ.
* Deadline.
* Kết quả.
* Trạng thái phê duyệt.

Hỗ trợ Kanban và bảng dữ liệu.

12.6. Learning Center

Hiển thị:

* Agent đang nghiên cứu gì.
* Tài liệu mới.
* Kiến thức mới.
* Nguồn tham khảo.
* Kinh nghiệm mới.
* Các bài học thành công.
* Các bài học thất bại.
* Đề xuất cải thiện.
* Phiên bản kiến thức.

12.7. Company Chat

Owner có thể nói chuyện với AI CEO để điều hành toàn hệ thống.

Ví dụ:

“Tìm 100 khách hàng tiềm năng có khả năng bán sỉ sản phẩm trà.”

AI CEO sẽ:

1. Hiểu mục tiêu.
2. Giao Sales Intelligence nghiên cứu.
3. Giao Affiliate Agent tìm đối tác.
4. Giao Data Analyst đánh giá dữ liệu.
5. Tổng hợp kết quả.
6. Trình bày báo cáo cho Owner.

⸻

PHẦN 13. AUTONOMY AND PERMISSION CONTROL

Hệ thống cần 4 cấp quyền:

Level 1: Read Only

* Nghiên cứu.
* Đọc dữ liệu.
* Phân tích.
* Đề xuất.

Level 2: Draft

* Tạo nội dung.
* Tạo bản nháp.
* Lập kế hoạch.
* Chuẩn bị chiến dịch.

Level 3: Execute

* Thực hiện công việc được cấp phép.
* Đăng nội dung đã duyệt.
* Đồng bộ dữ liệu.
* Gửi thông báo được phép.

Level 4: Advanced Automation

* Tự điều phối workflow.
* Tự tối ưu trong giới hạn.
* Tự thực hiện những hành động đã được phê duyệt trước.

Các hành động bắt buộc có Human Approval:

* Thay đổi giá sản phẩm.
* Tăng ngân sách quảng cáo vượt ngưỡng.
* Thanh toán.
* Xóa dữ liệu.
* Gửi chiến dịch hàng loạt.
* Thay đổi chính sách.
* Xuất bản nội dung có rủi ro pháp lý.
* Thay đổi quyền hạn Agent.

Mỗi hành động phải được ghi Audit Log.

⸻

PHẦN 14. SCHEDULER AND AUTONOMOUS OPERATIONS

Hệ thống phải hỗ trợ lịch hoạt động:

* Chạy nghiên cứu thị trường hàng ngày.
* Kiểm tra thứ hạng SEO.
* Kiểm tra hiệu quả quảng cáo.
* Tạo lịch nội dung.
* Tổng hợp báo cáo.
* Kiểm tra khách hàng tiềm năng.
* Đánh giá KPI Agent.
* Tạo báo cáo cuối ngày.

Ví dụ:

08:00 - AI CEO tổng hợp tình hình.
08:30 - Marketing Director lập kế hoạch.
09:00 - SEO và Content nghiên cứu.
10:00 - Creative sản xuất tài nguyên.
13:00 - Social Agent chuẩn bị nội dung.
15:00 - Data Analyst kiểm tra dữ liệu.
17:00 - Directors đánh giá.
18:00 - AI CEO báo cáo Owner.

Lịch là cấu hình thay đổi được, không hardcode.

Phải hỗ trợ:

* Retry.
* Timeout.
* Pause.
* Resume.
* Cancellation.
* Recovery sau khi restart.

⸻

PHẦN 15. SECURITY

Các yêu cầu bắt buộc:

1. Authentication.
2. Role-Based Access Control.
3. Agent Permission Control.
4. API Key Encryption.
5. Secret Management.
6. Audit Logging.
7. Rate Limiting.
8. Input Validation.
9. Output Validation.
10. Prompt Injection Protection.
11. File Upload Validation.
12. Database Backup.
13. Data Isolation.
14. Human Approval.

Không để Agent có quyền truy cập trực tiếp toàn bộ database.

Tất cả thao tác dữ liệu thông qua API và permission layer.

Agent không được:

* Tự nâng quyền.
* Đọc secret ngoài phạm vi.
* Tự sửa mã nguồn production.
* Tự xóa lịch sử kiểm toán.
* Tự thay đổi system security policy.

⸻

PHẦN 16. API DESIGN

Các API chính:

Agent API

POST /api/v1/agents

GET /api/v1/agents

GET /api/v1/agents/{agent_id}

PATCH /api/v1/agents/{agent_id}

POST /api/v1/agents/{agent_id}/chat

POST /api/v1/agents/{agent_id}/pause

POST /api/v1/agents/{agent_id}/resume

Brain API

GET /api/v1/agents/{agent_id}/brain

GET /api/v1/agents/{agent_id}/memory

GET /api/v1/agents/{agent_id}/knowledge

GET /api/v1/agents/{agent_id}/experience

POST /api/v1/agents/{agent_id}/learning

Task API

POST /api/v1/tasks

GET /api/v1/tasks

GET /api/v1/tasks/{task_id}

POST /api/v1/tasks/{task_id}/assign

POST /api/v1/tasks/{task_id}/approve

POST /api/v1/tasks/{task_id}/reject

POST /api/v1/tasks/{task_id}/cancel

Learning API

GET /api/v1/learning/sessions

POST /api/v1/learning/sessions

GET /api/v1/learning/knowledge-candidates

POST /api/v1/learning/knowledge-candidates/{id}/approve

Analytics API

GET /api/v1/analytics/overview

GET /api/v1/analytics/agents

GET /api/v1/analytics/costs

GET /api/v1/analytics/business

Tất cả API phải có authentication, authorization, validation và error handling.

⸻

PHẦN 17. CẤU TRÚC SOURCE CODE

ai-marketing-company/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── agents/
│   │   ├── orchestration/
│   │   ├── brains/
│   │   ├── memory/
│   │   ├── learning/
│   │   ├── knowledge/
│   │   ├── skills/
│   │   ├── tools/
│   │   ├── integrations/
│   │   ├── tasks/
│   │   ├── analytics/
│   │   ├── security/
│   │   ├── database/
│   │   └── main.py
│   │
│   ├── tests/
│   ├── migrations/
│   └── requirements.txt
│
├── frontend/
│   ├── app/
│   ├── components/
│   ├── modules/
│   ├── dashboard/
│   ├── agents/
│   ├── brain/
│   ├── memory/
│   ├── learning/
│   ├── tasks/
│   └── analytics/
│
├── infrastructure/
│   ├── docker/
│   ├── postgres/
│   ├── redis/
│   ├── monitoring/
│   └── backup/
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── API.md
│   ├── DATABASE.md
│   ├── AGENT_SPEC.md
│   ├── BRAIN_SPEC.md
│   ├── LEARNING_SPEC.md
│   ├── SECURITY.md
│   └── DEPLOYMENT.md
│
├── scripts/
├── docker-compose.yml
├── .env.example
├── README.md
└── CLAUDE.md

⸻

PHẦN 18. TESTING AND QUALITY ASSURANCE

Phải xây dựng:

Unit Tests

* Agent initialization.
* Brain loading.
* Memory retrieval.
* Permission checking.
* Task management.

Integration Tests

* Agent-to-Agent communication.
* Model Gateway.
* Database.
* Vector Search.
* API Integration.

Learning Tests

* Kiểm tra lưu kiến thức.
* Kiểm tra truy xuất kiến thức.
* Kiểm tra trùng lặp.
* Kiểm tra cập nhật phiên bản.
* Kiểm tra khả năng học từ phản hồi.

Security Tests

* Prompt Injection.
* Unauthorized Tool Access.
* Data Leakage.
* Permission Escalation.
* Secret Exposure.

Performance Tests

* Concurrent Agents.
* Queue Processing.
* Memory Retrieval.
* API Response Time.
* Model Cost Tracking.

⸻

PHẦN 19. ACCEPTANCE CRITERIA

Sản phẩm chỉ được nghiệm thu khi đáp ứng các tiêu chí:

1. Tạo và quản lý được ít nhất 15 Agent.
2. Mỗi Agent có Identity riêng.
3. Mỗi Agent có cấu hình Brain riêng.
4. Mỗi Agent có Private Memory.
5. Có Shared Knowledge.
6. Có Experience Memory.
7. Có cơ chế tìm kiếm bộ nhớ.
8. Có khả năng học từ tài liệu.
9. Có khả năng lưu kinh nghiệm từ nhiệm vụ.
10. Có AI CEO điều phối.
11. Các Agent trao đổi được với nhau.
12. Có hệ thống giao việc.
13. Có hệ thống phê duyệt.
14. Có Model Gateway.
15. Có Tool Registry.
16. Có Dashboard.
17. Có lịch hoạt động tự động.
18. Có Cost Tracking.
19. Có Audit Log.
20. Có Backup và Recovery.
21. Có khả năng mở rộng thêm Agent mà không sửa kiến trúc lõi.
22. Có khả năng thay đổi nhà cung cấp AI.
23. Có khả năng tạm dừng và khôi phục Agent.
24. Không để Agent vượt quyền được cấp.
25. Có bộ kiểm thử tự động.

Đặc biệt, phải chứng minh được mỗi Agent có thể:

* Ghi nhớ một kinh nghiệm.
* Truy xuất kinh nghiệm đó ở một phiên làm việc mới.
* Sử dụng kinh nghiệm trong nhiệm vụ tương tự.
* Được đánh giá bằng kết quả đầu ra.

⸻

PHẦN 20. DEVELOPMENT ROADMAP

Sprint 1: Foundation

* Setup Backend.
* Setup Frontend.
* Setup Database.
* Setup Redis.
* Setup Docker.
* Setup Authentication.
* Setup Model Gateway.

Sprint 2: Agent Core

* Agent Registry.
* Agent Lifecycle.
* Brain Loader.
* Agent Configuration.
* Tool Registry.
* Permission Manager.

Sprint 3: Memory System

* Private Memory.
* Shared Memory.
* Episodic Memory.
* Semantic Memory.
* Procedural Memory.
* Vector Search.

Sprint 4: Orchestration

* AI CEO.
* Director Agents.
* Task Engine.
* Message Bus.
* Agent Collaboration.

Sprint 5: Learning Engine

* Research Collector.
* Knowledge Extractor.
* Knowledge Validator.
* Experience Evaluator.
* Learning Scheduler.

Sprint 6: Initial Specialist Agents

* SEO.
* Content.
* Social.
* Creative.
* Data Analyst.

Sprint 7: Remaining Agents

* Ads.
* Customer.
* Affiliate.
* Sales Intelligence.
* Web CRO.
* Automation.

Sprint 8: Dashboard and Integration

* Agent Dashboard.
* Brain Dashboard.
* Learning Dashboard.
* Task Center.
* Business Analytics.
* Website Integration.

Sprint 9: Testing and Production

* Security.
* Performance.
* Integration Tests.
* Backup.
* Monitoring.
* Production Deployment.

⸻

PHẦN 21. YÊU CẦU ĐẶC BIỆT DÀNH CHO CLAUDE CODE

Đây là những yêu cầu bắt buộc khi phát triển.

1. Không xây dựng toàn bộ hệ thống trong một file.
2. Không viết Agent dưới dạng chatbot đơn giản.
3. Không dùng một bộ nhớ chung không phân quyền cho tất cả Agent.
4. Không hardcode AI Model Provider.
5. Không hardcode API Key.
6. Không bỏ qua hệ thống kiểm soát quyền.
7. Không tạo dữ liệu giả để giả lập chức năng production.
8. Không tự nhận đã hoàn thành chức năng khi chưa có test.
9. Không để lỗi của một Agent làm sập toàn hệ thống.
10. Không tạo kiến trúc phụ thuộc duy nhất vào một LLM.
11. Phải có Logging và Observability.
12. Phải có Documentation.
13. Phải có Migration.
14. Phải có Automated Tests.
15. Phải có Error Handling.
16. Phải có cơ chế Recovery.

Yêu cầu phát triển theo từng giai đoạn

Không được viết toàn bộ code ngay lập tức.

Quy trình bắt buộc:

BƯỚC 1:
Đọc toàn bộ tài liệu SRS.

BƯỚC 2:
Phân tích yêu cầu và thiết kế kiến trúc chi tiết.

BƯỚC 3:
Tạo tài liệu:

* IMPLEMENTATION_PLAN.md
* ARCHITECTURE.md
* DATABASE_SCHEMA.md
* AGENT_DESIGN.md
* SECURITY_PLAN.md
* TEST_PLAN.md

BƯỚC 4:
Đề xuất công nghệ và dependency.

BƯỚC 5:
Chờ Owner duyệt kiến trúc.

BƯỚC 6:
Triển khai từng Sprint.

BƯỚC 7:
Viết và chạy test sau từng module.

BƯỚC 8:
Cập nhật tài liệu sau mỗi lần thay đổi kiến trúc.

BƯỚC 9:
Tổng hợp báo cáo tiến độ và các chức năng còn thiếu.

DEFINITION OF DONE

Một module chỉ được xem là hoàn thành khi:

* Source code đã được triển khai.
* Có Unit Tests.
* Có Integration Tests khi cần.
* Tests đã chạy thành công.
* Có xử lý lỗi.
* Có logging.
* Có tài liệu.
* Có kiểm tra bảo mật.
* Có hướng dẫn sử dụng.

⸻

FINAL PRODUCT VISION

Sản phẩm cuối cùng phải là một AI Company có khả năng:

1. Tiếp nhận mục tiêu từ chủ doanh nghiệp.
2. Phân tích mục tiêu.
3. Xây dựng chiến lược.
4. Tự phân công công việc.
5. Các Agent nghiên cứu và phối hợp.
6. Tạo nội dung và tài nguyên Marketing.
7. Thực hiện các công việc được cấp quyền.
8. Theo dõi dữ liệu kinh doanh.
9. Đánh giá hiệu quả.
10. Tích lũy kinh nghiệm.
11. Cải thiện chất lượng công việc.
12. Báo cáo cho chủ doanh nghiệp.

Nguyên tắc cuối cùng:

Mỗi Agent là một nhân sự AI có bộ não chuyên môn, trí nhớ và kinh nghiệm riêng.

AI CEO là bộ phận điều hành.

Shared Knowledge là tri thức doanh nghiệp.

Learning Engine là hệ thống đào tạo và cải thiện.

Orchestration Engine là bộ phận điều phối.

Owner là người nắm quyền quản trị cao nhất.

Hệ thống phải được xây dựng theo hướng độc lập, mở rộng, có thể thay đổi mô hình AI, bổ sung Agent, nâng cấp bộ não và phát triển thành một doanh nghiệp AI tự vận hành thực sự.

2. Cách giao tài liệu này cho Claude Code

Tôi khuyên bạn không nên chỉ dán đặc tả rồi yêu cầu Claude viết tất cả code trong một lần. Hãy để Claude làm kiến trúc sư trước, sau đó mới giao từng Sprint.

Bạn có thể dùng câu lệnh đầu tiên sau:

Bạn là Principal Software Architect và Senior AI Engineer.

Hãy đọc toàn bộ tài liệu SRS của dự án AI Marketing Company.

Nhiệm vụ đầu tiên của bạn KHÔNG PHẢI viết code ngay.

Hãy thực hiện:

1. Phân tích toàn bộ yêu cầu.
2. Xác định các thành phần kỹ thuật.
3. Thiết kế kiến trúc hệ thống hoàn chỉnh.
4. Thiết kế database và các quan hệ.
5. Thiết kế kiến trúc bộ não riêng cho từng Agent.
6. Thiết kế hệ thống Private Memory và Shared Memory.
7. Thiết kế Learning Engine.
8. Thiết kế Multi-Agent Orchestration.
9. Thiết kế quyền hạn và bảo mật.
10. Đánh giá khả năng mở rộng lên 100 Agent.

Tạo đầy đủ các tài liệu kỹ thuật cần thiết.

Đối với mỗi quyết định kiến trúc, hãy nêu rõ:

* Lý do lựa chọn.
* Ưu điểm.
* Nhược điểm.
* Chi phí vận hành dự kiến.
* Khả năng mở rộng.

Không tự ý lược bỏ chức năng trong SRS.

Nếu có yêu cầu chưa rõ hoặc có rủi ro kỹ thuật, hãy lập danh sách để hỏi Owner.

Sau khi hoàn thành thiết kế, hãy trình bày kế hoạch triển khai theo Sprint và chờ phê duyệt trước khi bắt đầu phát triển.

3. Những module tôi khuyên bạn ưu tiên nhất

Không phải giao diện đẹp hay số lượng Agent là quan trọng nhất. Có 4 module quyết định chất lượng của toàn hệ thống:

1. Individual Brain Engine

Ưu tiên cao nhất

Tạo ra sự khác biệt giữa các Agent, quản lý trí nhớ và kiến thức chuyên môn.

2. Multi-Agent Orchestrator

Giúp các Agent biết phối hợp và làm việc như một tổ chức.

3. Continuous Learning Engine

Giúp Agent tích lũy kinh nghiệm, học từ kết quả và cải thiện năng lực.

4. Agent Control Center

Giúp bạn theo dõi, quản lý, kiểm tra và điều hành toàn bộ đội ngũ AI.

Một lưu ý kỹ thuật rất quan trọng: Muốn Agent thực sự giỏi lên theo thời gian, cần xây dựng bộ đánh giá chất lượng độc lập. Không được để Agent tự chấm điểm câu trả lời của chính mình rồi tự kết luận đã tiến bộ. Phải đo bằng dữ liệu, kết quả công việc, tiêu chí kiểm thử và phản hồi của con người.

4. Bước tiếp theo tôi đề xuất

Trước khi triển khai, nên có thêm một tài liệu riêng gọi là Agent Brain Blueprint. Tài liệu này sẽ mô tả sâu cách thiết kế trí nhớ, tư duy, học tập, tính cách, kỹ năng và cơ chế phát triển năng lực cho từng Agent.

Đây chính là phần quyết định đội ngũ AI của bạn chỉ là các chatbot được phân vai, hay thực sự trở thành một tổ chức AI có chuyên môn và kinh nghiệm tích lũy.