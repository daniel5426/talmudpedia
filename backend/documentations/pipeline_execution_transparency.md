# Pipeline Execution Transparency

The Pipeline Execution Transparency feature provides real-time visibility and debugging capabilities for RAG pipelines. It allows users to track the execution flow, inspect data at each step, and quickly identify bottlenecks or errors.

## Features

### 1. Live Execution Tracking
When a pipeline is executed, users can see the progress directly on the visual builder canvas:
- **Spinning Loader**: Indicates the node currently being processed.
- **Color Coding**: Status-based borders (blue for running, green for completed, red for failed).
- **Status Icons**: Overlays onto nodes showing individual step completion or failure.

### 2. Step-by-Step Data Inspection
Users can click on any executed node to open the **Execution Details Panel**:
- **Input Data**: View the exact data received by the operator.
- **Output Data**: View the results produced by the operator.
- **Timing**: Verification of start and completion times.
- **Error Messages**: Detailed tracebacks and error messages if a node fails.

### 3. Progressive Transparency
The system doesn't wait for the entire job to finish. It streams execution steps as they happen, allowing for:
- **Instant Feedback**: Source nodes start spinning immediately after trigger.
- **Real-time Debugging**: Catch errors in the middle of a large DAG without waiting for timeouts.

## Implementation Details

### Backend Architecture
- **Database**: A new table `pipeline_step_executions` was introduced to store granular state.
- **Executor Integration**: The `PipelineExecutor` was refactored with a `handle_step_execution` context manager that automatically logs:
    - Status transitions (`running`, `completed`, `failed`).
    - Input params and output results (truncated if too large).
    - Exception details.
- **API**: New endpoints under `/api/v1/rag/pipelines/jobs/{job_id}/steps` allow fetching the execution history of a job.

### Frontend Integration
- **State Management**: The `PipelineBuilder` syncs execution metadata with the React Flow node state.
- **Optimistic UI**: To improve perceived performance, the frontend optimistically marks source nodes as `running` as soon as the API call successfully starts the background job.
- **Side Panel**: A dedicated `ExecutionDetailsPanel` component was added to the builder to render JSON data and status information.

## How to use
1. Go to the **Pipeline Editor**.
2. **Compile** your pipeline to ensure it's valid.
3. Click **Run Pipeline** and provide any required input parameters.
4. Watch the nodes execute in real-time.
5. Click on any node to see what went in and what came out.
