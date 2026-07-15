# LangSmith Masterclass - English Conversion

Source: attached Hindi/Hinglish YouTube transcript.

Note: This is a cleaned English conversion of the transcript. It preserves the structure, timestamps, examples, technical explanations, and main teaching flow, while removing repeated filler and conversational repetition.

## 0:00 - Introduction

Hi guys, my name is Nitesh, and welcome to my YouTube channel. In this video, we are going to cover a very important GenAI topic: LangSmith.

So far, we have been covering the GenAI syllabus in a structured way. We started with LangChain, then began LangGraph, which is still in progress. But while studying LangGraph, we have reached a stage where we need to understand how observability is implemented in LLM applications. That is why I thought we should take a small detour and study LangSmith.

LangSmith is a powerful observability and evaluation tool that you can integrate into LLM applications. In today's video, I will first give you the theoretical background: why LangSmith is needed and what observability means for an LLM system. Then I will practically show you how to integrate LangSmith with both LangChain and LangGraph. At the end, I will also give you an idea of an emerging related field called LLMOps.

If you watch the full video, I am sure you will learn something new and important. There is only one disclaimer: if you want to follow this video completely, you should already have some idea of LangChain and the parts of LangGraph I have taught so far. If you know these two things, understanding today's video will be much easier.

## 1:57 - Why LangSmith?

Before studying LangSmith in detail, let us first discuss why tools like LangSmith are needed. We will use some real-world scenarios.

### Scenario 1: Debugging Latency In An LLM Workflow

Imagine you work at a startup. Your team identifies a problem students face when they graduate from college and start applying for jobs. The usual process is repetitive: students go to job websites, filter jobs, study job descriptions, modify their resumes and cover letters according to each job description, and then apply.

The problem is that students may need to do this ten or more times a day. They do not want to send the same resume and cover letter everywhere. They want each employer to feel that they made an effort.

So your team builds an LLM-based application. A student enters a job description link or uploads a PDF. The tool studies the job description, accesses the student's Google Drive to fetch their portfolio, resume, projects, and other details, matches the student's relevant skills with the job requirements, generates a job-specific cover letter, proofreads it, checks the tone, and finally returns a polished cover letter. Students can use this tool repeatedly throughout the day.

The tool becomes popular. Users like it and use it daily. Normally, the system takes about two minutes from input to output. But suddenly, on a particular day, users start emailing that the website has become very slow. The same task that used to take two minutes now takes seven to ten minutes. Users become frustrated and start leaving the platform, which means revenue loss.

Now you need to debug the system quickly. But the system is a complex LLM workflow with multiple stages: reading the job description, fetching the student's documents, matching skills, generating the cover letter, and proofreading it. You only know the user input, the final output, and the total time taken. You do not know how much time each internal stage took.

Maybe a recent code update accidentally made the Google Drive step scan the entire drive instead of one specific folder. That could be where the extra eight minutes are being spent. But without a way to see inside the workflow step by step, you cannot identify the culprit.

This is where a tool like LangSmith comes into the picture.

### 8:34 - Example 2: Debugging Cost In An Agent

Now consider a second example: a research assistant agent. You and your team build an agent that helps researchers. A researcher enters a topic, such as solar energy. The tool fetches related academic papers from sources like Google Scholar or arXiv, studies each paper, extracts key points, summarizes them, produces a report, and then allows the user to chat with that report and ask questions.

Users like the tool and pay for it. Suppose generating one report usually costs around 50 paise because you are using LLM APIs and paying for tokens. You price the product accordingly and your business works.

But one day you notice that your OpenAI dashboard cost has suddenly increased. After some investigation, you find that some reports still cost 50 paise, while others suddenly cost around 2 rupees. At scale, that spike can become a major loss.

Now you need to debug the agent. Agents are autonomous software systems. You give them a goal, and they reason, take actions, observe results, decide whether the goal has been achieved, and keep looping until they think the goal is complete.

Suppose in your last update you made a small prompt change: "keep generating the report until it is excellent." You made this change to improve user experience. But now, for some topics, the agent is not satisfied with its own output. It goes back to Google Scholar, downloads papers again, studies them again, extracts points again, summarizes again, and repeats the entire process. Some reports finish normally, but others loop extra times and become expensive.

There may be no code error or exception. The agent is simply behaving differently. The behavior changes only in certain scenarios. This makes debugging very difficult. You need a tool that turns the black box into a white box and lets you inspect every internal step.

### Third Example: RAG Hallucination In A Company Chatbot

Now consider a RAG use case. Suppose you are a senior software developer at a large company like TCS. The company has many employees and thousands of freshers join every year. They often have questions about leave policies, notice periods, health insurance, salary rules, and internal processes. HR teams repeatedly answer the same questions, which reduces productivity.

You decide to build a RAG-based chatbot. You collect company documents, create a knowledge base, and allow employees to ask natural language questions. The chatbot retrieves relevant documents and passes them with the user's question to an LLM, which generates an answer.

Initially, the system works well. Freshers ask questions and get answers, reducing pressure on HR. But later, teammates complain that the chatbot has started hallucinating. For example, an employee asks about leave policy, and the chatbot says, "No problem, take leave whenever you want; go to Goa if you want." The employee might trust that because the answer came from the company chatbot. This can create serious misinformation.

A RAG system usually hallucinates for two broad reasons. First, the retriever may fetch the wrong documents. If the user asks about notice period but the retriever fetches documents about company history, the LLM will not have the right context. Second, the generator may be the problem. The LLM may ignore the context, use a weak prompt, or hallucinate instead of saying "I don't know."

Without internal visibility, you cannot tell whether the retriever failed or the generator failed. You cannot see which documents were retrieved or what final prompt was sent to the LLM. So again, you need a tool that shows every internal component and every intermediate state.

These three scenarios show the need for observability: latency problems, cost problems, and hallucination problems.

## 22:20 - Observability

Observability is the ability to understand a system's internal state by examining the data it produces, such as logs, metrics, and traces. It helps you diagnose issues, understand performance, and improve reliability. Essentially, observability lets you answer why something is happening inside a system, even if you did not anticipate the problem beforehand.

LLM systems are difficult because their behavior is non-deterministic. In ordinary software, if you provide the same input, you usually get the same output. For example, a calculator will always return 8 for 2 * 4. But LLM-based systems can produce different outputs for the same or similar input. Because of this, problems like latency, cost spikes, and hallucinations often do not leave a clean error trace.

LLM applications are also complex and black-box-like. That is why debugging them in production becomes difficult. Observability helps by opening up the system so you can see what happens component by component.

LangSmith is a unified observability and evaluation platform where teams can debug, test, and monitor AI application performance. In short, LangSmith lets you bring observability into LLM applications. When you execute an LLM application, LangSmith traces the full execution and shows what input each component received, what output it produced, how long it took, and other details at a granular level.

The practical plan is to first integrate LangSmith with LangChain, then with LangGraph. We will test simple workflows, RAG workflows, and agentic workflows so you get an end-to-end idea of how LangSmith helps implement observability in any kind of LLM workflow.

## 26:35 - What Does LangSmith Trace?

When you log an execution in LangSmith, it can trace:

- The input and output of each execution.
- Intermediate states and intermediate steps.
- For a RAG system, the question sent to the retriever, the context retrieved, the prompt formed from question and context, the LLM response, and the output parser result.
- Latency at the application level and at the component level.
- Token usage and cost, including input and output tokens.
- Errors in any component.
- Tags and system-generated tags, such as the model name.
- Custom metadata and system metadata, such as the LangChain version and dependencies.
- User feedback attached to traces.

## 29:04 - Setting Up The Project

The setup begins by cloning the GitHub repository for the code used in the video. The repository link is in the video description. After cloning it, open the folder in VS Code.

Then create and activate a virtual environment. After that, install dependencies from `requirements.txt` using:

```bash
pip install -r requirements.txt
```

While the libraries install, create a LangSmith account. In LangSmith, go to settings and generate an API key. Use a personal access token and set the expiry as needed.

Next, create a `.env` file in the project and add the required environment variables:

- OpenAI API key, because the demos use OpenAI models.
- LangChain tracing enabled, usually `LANGCHAIN_TRACING_V2=true`.
- LangSmith endpoint.
- LangSmith API key.
- LangSmith project name.

The project name controls where traces are grouped in LangSmith. For example, if the project name is `langsmith-demo`, LangSmith creates or uses a project with that name and stores traces there.

## 34:57 - Core Concepts: Project, Trace, And Run

Before tracing the first project, three LangSmith concepts are important:

- Project
- Trace
- Run

Suppose you build a simple LLM app. The user enters a question, the question is inserted into a prompt, the prompt goes to an LLM, the LLM returns a response, and a parser formats the output for the user.

In LangSmith, the whole application is a project. Every single end-to-end execution of that application is a trace. During each trace, every component execution is a run. In the simple example, the prompt template is one run, the LLM call is another run, and the output parser is another run.

So the application is the project, each execution is a trace, and each component inside the trace is a run.

## 38:02 - First Code Demo: Simple LLM Call

The first file is a simple LLM call. It creates a basic chain made of a prompt, a model, and a string output parser. The question is sent to the model and the response is parsed.

When the code is run with a question like "What is the capital of Peru?", the answer is "Lima." Even though the code does not explicitly mention LangSmith, the trace appears automatically because the `.env` file already contains the LangSmith endpoint, API key, and tracing flag.

In the LangSmith UI, go to tracing projects. A project with the configured name appears. Inside that project, each execution appears as a trace. The trace shows:

- Input question.
- Output answer.
- Whether there was an error.
- Latency.
- Token usage.
- Estimated cost.

Clicking a trace opens the detailed run view. For the simple app, the runs are the prompt template, ChatOpenAI, and the string output parser. Each run shows its own input, output, latency, and details.

If you run the same file again with a different input, such as asking about India instead of Peru, a second trace appears in the same project. This demonstrates how LangSmith organizes work as projects, traces, and runs.

## Sequential Chain Demo

The next example uses a sequential two-step LLM application. First, the model generates a detailed report on a topic. Then a second prompt asks the model to generate a five-point summary from that report.

The code sets a project name from inside Python using an environment variable, so this example appears in its own LangSmith project. It also explicitly sets models, for example `gpt-4o-mini` for one step and `gpt-4o` for another. The demo also shows how to attach custom tags and metadata when invoking the chain.

Example tags:

- `llm-app`
- `report-generation`
- `summarization`

Example metadata:

- model names
- temperature values
- parser name

In LangSmith, the trace shows the full sequence: first prompt, first model call, parser, second prompt, second model call, and parser. The tags and metadata are searchable and visible in the UI. The demo also shows that you can set a custom run name instead of accepting the auto-generated `RunnableSequence` name.

## 54:23 - Tracing A RAG Application

RAG, or retrieval augmented generation, means giving an LLM both a user query and additional relevant context retrieved from your own documents. For example, if you want question answering over personal or company documents, you retrieve relevant chunks and send them to the LLM with the question.

In theory, RAG sounds simple. In practice, RAG chatbots often produce low-quality answers. There are two main failure types:

- Retriever errors: the retriever fails to fetch relevant chunks.
- Generator errors: the retriever fetched good chunks, but the LLM still hallucinated or produced a poor answer.

If you only see the final answer, you cannot know whether the retriever or the generator failed. LangSmith solves this by tracing every intermediate step: the user question, retrieved documents, final prompt, and LLM response.

The demo uses a PDF of *Introduction to Statistical Learning*. The RAG app loads the PDF, chunks it, embeds it, creates a retriever, and answers questions like "Who is the author of this book?" or "What is the summary of chapter 6?"

The basic chain has two parts. A parallel chain passes through the original question and also sends the question to the retriever to get context. Then the question and context are passed into a prompt, then to the LLM, then to a string output parser.

When this app is traced in LangSmith, the query part is visible: question, retriever, context, prompt, LLM, parser. But there are two problems.

First, the entire RAG application is not being traced. The PDF loading, chunking, and embedding steps are not automatically traced because they are normal Python code, not LangChain runnables. LangSmith traces LangChain runnables by default, but not arbitrary Python functions unless you instrument them.

Second, the app has a latency problem. Every time the app runs, it loads the same PDF, chunks it again, and generates embeddings again. That is inefficient. Ideally, the PDF should be processed once, embeddings should be stored, and later runs should reuse the existing index.

## Using `traceable` For Normal Python Functions

To trace the full RAG setup pipeline, the code is refactored into functions:

- `load_pdf`
- `split_documents`
- `build_vector_store`
- `setup_pipeline`

Each function is decorated with LangSmith's `traceable` decorator and given a meaningful name. This allows LangSmith to trace normal Python functions even if they are not LangChain runnables.

After this change, the LangSmith UI shows a setup pipeline trace containing runs for loading the PDF, splitting documents, and building the vector store. You can inspect inputs, outputs, latency, and other details for each step.

The demo also shows that each traceable function can have its own tags and metadata. For example, the PDF loader step can have tags like `pdf` and `loader`, and metadata such as `loader: PyPDFLoader`. The vector store step can have metadata such as the embedding model name and embedding dimensions. This metadata becomes searchable across traces.

## Fixing RAG Latency With A Stored FAISS Index

To fix repeated setup latency, the next version uses FAISS. On the first run, the app builds an index from the PDF and stores it in the project directory. On later runs, it checks whether the index already exists and reuses it instead of rebuilding it.

The first run still takes time because the PDF must be loaded, chunked, embedded, and indexed. But later runs are much faster because they load the existing index. The trace clearly shows whether the app is building the index or loading an existing one.

The index is rebuilt only when needed, such as:

- The app runs for the first time and no index exists.
- The PDF path or PDF content changes.
- File metadata such as size or last modified time changes.
- Chunking parameters such as chunk size or chunk overlap change.
- The embedding model changes.

This is the pattern you normally want in production RAG applications: build and maintain an index, then reuse it for queries instead of rebuilding everything every time.

## 1:24:11 - Tracing An Agentic Application

The next demo traces an agent. The agent uses tools such as DuckDuckGo search and a weather API. The first example asks for the release date of a movie. LangSmith shows the full ReAct-style flow:

- The agent scratchpad starts empty.
- A prompt is created with the question and available tools.
- The LLM decides what action to take.
- The action calls DuckDuckGo search.
- The observation from the tool is added back to the scratchpad.
- A new prompt is formed with the scratchpad.
- The LLM produces the final answer.

Because of LangSmith, you can see every thought, action, observation, prompt, tool input, tool output, and final answer. This makes agent behavior much more transparent.

## 1:27:12 - Testing Agent Queries

The second agent query asks for the current temperature in Gurgaon. The LLM chooses the weather tool, passes `Gurgaon` as input, receives weather data such as temperature, humidity, and wind speed, and returns the final temperature.

The next query is more complex: identify Kalpana Chawla's birthplace and then give the current temperature there. This forces the agent to use two tools. First it searches for Kalpana Chawla's birthplace, identifies Karnal, then calls the weather tool for Karnal, and finally returns the temperature.

LangSmith makes the multi-step process visible. You can inspect each search, each tool call, the scratchpad updates, and the final answer. This is especially useful for debugging complex agents, where a single wrong tool decision can change the entire result.

The instructor emphasizes that if you build agentic applications, you should integrate LangSmith. For more complex hiring platforms, research agents, or workflow agents, debugging without traces becomes very difficult.

## 1:33:58 - LangGraph And LangSmith Integration

LangGraph is a library for building LLM applications as workflows represented as graphs. Nodes represent tasks, edges define which task runs next, and state flows through the graph.

As LangGraph workflows become complex, debugging becomes hard. LangSmith has strong integration with LangGraph because both tools come from the same ecosystem. In LangGraph, one full graph execution becomes a LangSmith trace, and each node execution becomes a run inside that trace.

The demo uses a LangGraph workflow for evaluating a UPSC essay. The graph evaluates the essay across multiple dimensions such as language, analysis, and clarity. These evaluations run in parallel, and their outputs go to a final evaluation node, which produces overall feedback and an average score.

In the LangSmith dashboard, the graph execution appears as a trace. The parallel nodes appear as runs, and the final evaluation node appears after them. You can inspect each node's input state, output state, internal LLM calls, structured output schema, latency, token usage, and cost.

The demo also shows structured LLM output. For evaluation nodes, the model is wrapped with structured output so it returns fields like `feedback` and `score` according to a schema. LangSmith shows the internal runnable sequence and how the schema-shaped output is produced.

The key idea is simple: the full LangGraph execution is a trace, and each node is a run. You can name nodes, name functions, attach tags and metadata, and inspect how much time and cost each node consumed. This makes LangSmith both a debugging tool and a learning tool for understanding how complex graphs execute.

## 1:47:26 - Other Features Of LangSmith

So far, the discussion has focused mostly on observability: tracing an LLM application end to end. But LangSmith does more than observability.

### Monitoring And Alerting

Observability focuses on a single trace. Monitoring looks across many traces at once to understand the health of the LLM system. LangSmith can aggregate metrics such as latency, token usage, cost, error rates, and success rates.

For example, you can monitor the average latency across all traces for a day, the average token usage, total cost, or cost per trace. If latency suddenly starts increasing, that is an important signal.

LangSmith also supports alerts. You can set a threshold, such as "raise an alert if latency goes above five seconds." This helps you respond before users start complaining.

Production issues often first appear as patterns across many runs rather than in one individual trace. Monitoring helps catch early signals, such as performance degradation or cost spikes, before they affect users at scale.

### Evaluation

LLMs are probabilistic and non-deterministic. A small change in prompt, model, retrieval logic, or system configuration may improve some cases but break others. Evaluation gives you an objective and repeatable way to measure performance over time, verify that a new version is actually better, and prevent regressions.

LangSmith evaluation helps systematically measure output quality. You can run tests against gold-standard datasets or apply custom metrics such as faithfulness, relevance, completeness, hallucination checks, conciseness checks, code checks, and more.

LangSmith supports multiple evaluation approaches, including automated scoring with an LLM as judge, semantic similarity checks, custom Python evaluators, online evaluation, and offline evaluation.

You can set up evaluators inside a project, use your own data, create datasets from scratch, use prebuilt evaluators, or define your own custom evaluators.

This broader area is part of LLMOps: the discipline of building, evaluating, monitoring, and operating LLM systems reliably in production.

### Prompt Experimentation

Prompting is central to generative AI. The quality of an LLM application often depends heavily on prompt quality. But if you have Prompt A and Prompt B, how do you know which one is better? Running them once manually in ChatGPT is not conclusive.

Prompt experimentation means testing prompts systematically on the same dataset using evaluation criteria. LangSmith helps with this. You can run A/B tests across prompt versions, track performance against evaluation metrics, and record outcomes over time. This gives you a history of which prompt variations worked best and under what conditions.

LangSmith also provides a prompt engineering playground where you can compare prompts, schemas, evaluation criteria, and even models. For example, you can test the same prompt on two different models and compare results.

LangSmith also supports prompt versioning and collaboration. You can store prompts, version them, collaborate with teammates, and explore public prompts through LangChain Hub.

### Dataset Creation And Annotation

Evaluation requires standardized datasets. You can use public datasets or create datasets specific to your own use case. LangSmith provides tools to build datasets for evaluation and fine-tuning.

You can manually annotate examples, label whether outputs were correct or incorrect, and version datasets for reuse across projects. For example, if you are building a customer chatbot, you can create a dataset of common questions and expected answers. That dataset can be reused to test future versions of the app.

You can create a new dataset from the evaluation section, import existing rows, create an empty dataset, or add traces directly into a dataset. You can also send examples into an annotation queue and label them manually.

### User Feedback Integration

ChatGPT shows thumbs-up and thumbs-down options below responses. That kind of feedback tells the system whether users liked a response. LangSmith lets you add similar feedback mechanisms to your own LLM apps.

LangSmith can capture thumbs-up/down ratings or structured feedback from users in production. The feedback is stored alongside traces and tied to the exact prompt, model, and state that produced the response. You can then analyze what users liked or disliked across traces.

In the LangSmith UI, each trace can have feedback attached. Monitoring views can aggregate feedback scores across traces, helping you understand user sentiment toward your LLM application.

### Collaboration

LangSmith is designed for teams. Before tools like LangSmith, collaboration often meant taking screenshots and sending emails when latency, cost, or output quality looked wrong.

With LangSmith, traces are properly recorded and shareable. You can copy a trace link and send it to a teammate. They can open the same trace, inspect the exact same execution, and study the issue.

Teams can also collaborate on prompt versions, invite collaborators, create custom dashboards, and share those dashboards. This is very helpful when working in large teams.

## 2:06:29 - Wrap-Up

In this video, we studied LangSmith in detail. The main focus was observability, but LangSmith can do much more. We covered:

- Observability and tracing.
- Monitoring and alerting.
- Evaluation.
- Prompt experimentation.
- Dataset creation and annotation.
- User feedback integration.
- Collaboration.

All of these broadly fall under LLMOps. Building an LLM app is one thing. Running it effectively in production without problems is a completely different challenge.

## 2:07:26 - Outro

I hope you liked this two-to-two-and-a-half-hour video, gained perspective, and learned something new. If you liked the video, please like it. If you have not subscribed to the channel, please subscribe. See you in the next video. Bye.
