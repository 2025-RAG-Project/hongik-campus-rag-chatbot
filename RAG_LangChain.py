import pandas as pd
import uuid
import time
from langchain_openai import ChatOpenAI
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain.tools import tool
from langchain_experimental.agents.agent_toolkits import create_pandas_dataframe_agent
from dotenv import load_dotenv
from typing import Dict, Any


## 1. 전역 설정 및 초기화 함수
# 세션 기록 저장을 위한 전역 저장소 (실제 앱에서는 DB나 Redis 사용 권장)
STORE: Dict[str, ChatMessageHistory] = {}

def get_session_history(session_id: str) -> ChatMessageHistory:
    """세션 ID에 해당하는 ChatMessageHistory 객체를 반환합니다."""
    if session_id not in STORE:
        STORE[session_id] = ChatMessageHistory()
    return STORE[session_id]

def initialize_rag_agent(api_key_path: str, data_path: str, model_name: str = 'gpt-4o-mini') -> RunnableWithMessageHistory:
        
    # 0. .env 파일 읽어오기
    load_dotenv(api_key_path)

    # 1. LLM 정의 및 DataFrame 호출
    llm = ChatOpenAI(model=model_name, temperature=0)
    df = pd.read_csv(data_path, encoding='utf-8')

    
    # 2. DataFrame RAG Tool 생성
    # LangChain Experimental 모듈 사용
    df_agent_executor = create_pandas_dataframe_agent(
        llm,
        df,
        verbose=False,
        allow_dangerous_code=True
    )

    # Tool 정의 (Agent가 사용할 수 있도록 래핑)
    @tool
    def df_query_tool(query: str) -> str:
        """DataFrame에 대한 질문을 통해 데이터를 검색하고 계산합니다. 공지사항, 모집 정보 등의 데이터를 분석할 때 사용합니다."""
        result = df_agent_executor.invoke({"input": query})
        # 결과가 딕셔너리 형태일 경우 'output' 키를 반환
        if isinstance(result, dict):
            return str(result.get("output", result))
        return str(result)

    tools = [df_query_tool]

    # 3. Prompt 및 Agent Executor 정의
    prompt = ChatPromptTemplate.from_messages([
        ('system', '당신은 친절한 챗봇입니다. 질문에 답할 때, 반드시 제공된 도구(DataFrame)를 활용하여 데이터를 분석하세요.'),
        MessagesPlaceholder(variable_name='history'),
        ('human', "{input}"),
        MessagesPlaceholder(variable_name='agent_scratchpad')
    ])

    agent = create_tool_calling_agent(llm, tools, prompt)
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors=True
    )

    # 4. 최종 RunnableWithMessageHistory 정의 (메모리 적용)
    runnable = RunnableWithMessageHistory(
        agent_executor,
        get_session_history,
        input_messages_key='input',
        history_messages_key='history'
    )
    
  return runnable


## 2. 챗봇 실행 함수
def run_chatbot_cli(runnable: RunnableWithMessageHistory):

    session_id = str(uuid.uuid4())
    config = {"configurable": {"session_id": session_id}}

    print("--- 대화 시작 ---")
    print("종료하려면 'quit', 'exit', '종료' 중 하나를 입력하세요.\n")

    while True:
        user_input = input("당신의 메시지를 입력하세요: ")

        # 종료 조건
        if user_input.lower() in ['quit', 'exit', '종료']:
            print("챗봇을 종료합니다.")
            break

        # 사용자 입력 처리
        if user_input.strip():
            print("\n--- 응답 ---")
            # Runnable 실행
            response = runnable.invoke({"input": user_input}, config=config)
            print(response["output"])
            print()


## 3. 메인 실행 블록
if __name__ == "__main__":
    # 사용자 환경에 맞는 파일 경로를 정의합니다.
    API_KEY_FILE = r'C:\Langchain_Streanlit_Project\OPENAI_API_KEY.env'
    DATA_FILE = r'C:\Langchain_Streanlit_Project\df_academic_board_master.csv'

    # 1. RAG 에이전트 초기화
    rag_runnable = initialize_rag_agent(
        api_key_path=API_KEY_FILE,
        data_path=DATA_FILE
    )
    
    # 2. 챗봇 실행
    run_chatbot_cli(rag_runnable)
