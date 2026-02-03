import traceback
import asyncio
from typing import Dict, Any, List, Optional
from uuid import UUID
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.postgres.models.rag import PipelineJob, PipelineJobStatus, ExecutablePipeline, CustomOperator, PipelineStepExecution, PipelineStepStatus
from app.rag.pipeline.registry import OperatorRegistry, OperatorSpec, OperatorCategory, DataType, ConfigFieldSpec
from app.rag.pipeline.operator_executor import (
    ExecutorRegistry, 
    OperatorInput, 
    ExecutionContext,
    OperatorOutput
)

class PipelineExecutor:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.registry = OperatorRegistry.get_instance()

    def _get_runtime_input(self, input_params: Any, step_id: str) -> Any:
        """Resolve runtime input for a specific step."""
        if not isinstance(input_params, dict):
            return input_params
        step_params = input_params.get(step_id)
        if isinstance(step_params, dict):
            return step_params
        return input_params

    async def _sync_custom_operators(self, tenant_id: UUID):
        stmt = select(CustomOperator).where(CustomOperator.tenant_id == tenant_id)
        result = await self.db.execute(stmt)
        custom_ops = result.scalars().all()
        
        specs = []
        for op in custom_ops:
            # Parse config schema
            required_config = []
            if op.config_schema:
                for field in op.config_schema:
                    try:
                        required_config.append(ConfigFieldSpec(**field))
                    except Exception:
                        pass # Skip invalid fields

            spec = OperatorSpec(
                operator_id=op.name,
                display_name=op.display_name,
                category=OperatorCategory(op.category),
                description=op.description,
                input_type=DataType(op.input_type),
                output_type=DataType(op.output_type),
                is_custom=True,
                python_code=op.python_code,
                required_config=required_config,
                version="1.0.0"
            )
            specs.append(spec)
        
        self.registry.load_custom_operators(specs, str(tenant_id))

    async def execute_job(self, job_id: UUID):
        """
        Execute a pipeline job.
        This method is designed to be run as a background task.
        """
        # 1. Fetch Job
        job = await self.db.get(PipelineJob, job_id)
        if not job:
            print(f"Job {job_id} not found")
            return

        try:
            # Update status to running
            job.status = PipelineJobStatus.RUNNING
            job.started_at = datetime.utcnow()
            
            # 2. Fetch Executable Pipeline
            exec_pipeline = await self.db.get(ExecutablePipeline, job.executable_pipeline_id)
            if not exec_pipeline:
                 raise ValueError(f"Executable pipeline {job.executable_pipeline_id} not found")
            
            # 3. Sync Custom Operators
            await self._sync_custom_operators(job.tenant_id)
            
            # 4. Initialize Execution Steps
            dag_steps = exec_pipeline.compiled_graph.get("dag", [])
            step_executions = {}
            
            for i, step_data in enumerate(dag_steps):
                step_id = step_data.get("step_id")
                op_id = step_data.get("operator")
                
                step_exec = PipelineStepExecution(
                    job_id=job.id,
                    tenant_id=job.tenant_id,
                    step_id=step_id,
                    operator_id=op_id,
                    status=PipelineStepStatus.PENDING,
                    execution_order=i
                )
                self.db.add(step_exec)
                step_executions[step_id] = step_exec
            
            # Commit job start and step initialization
            await self.db.commit()

            # 5. Execute Steps
            results: Dict[str, OperatorOutput] = {}
            
            for step_data in dag_steps:
                step_id = step_data.get("step_id")
                op_id = step_data.get("operator")
                config = step_data.get("config", {})
                depends_on = step_data.get("depends_on", [])

                # Get the step execution record
                step_exec = step_executions.get(step_id)
                if step_exec:
                    step_exec.status = PipelineStepStatus.RUNNING
                    step_exec.started_at = datetime.utcnow()
                    await self.db.commit()

                try:
                    # Prepare Input
                    input_data = None
                    input_metadata = {}
                    
                    if not depends_on:
                        # Source node - use job input params
                        input_data = self._get_runtime_input(job.input_params, step_id)
                    else:
                        # Gather inputs from dependencies
                        collected_data = []
                        
                        for dep_id in depends_on:
                            if dep_id in results and results[dep_id].success:
                                 res = results[dep_id]
                                 if res.data is not None:
                                     if isinstance(res.data, list):
                                         collected_data.extend(res.data)
                                     else:
                                         collected_data.append(res.data)
                                 
                                 # Merge metadata
                                 input_metadata.update(res.metadata)
                        
                        input_data = collected_data
                    
                    if step_exec:
                        # Log input data (be careful with size?)
                        # For now logging it all, maybe need truncation later
                        try:
                            step_exec.input_data = input_data
                        except Exception:
                            # Fallback if specific data isn't JSON serializable or too large
                            step_exec.input_data = {"error": "Could not serialize input"}
                        await self.db.commit()

                    # Create Executor
                    # Ensure we check for tenant-specific custom operators
                    spec = self.registry.get(op_id, str(job.tenant_id))
                    
                    if not spec:
                         # Fallback: try to find it in general registry if not found with tenant
                         spec = self.registry.get(op_id)
                    
                    if not spec:
                         raise ValueError(f"Operator {op_id} not found in registry")

                    executor = ExecutorRegistry.create_executor(spec, spec.python_code)
                    
                    context = ExecutionContext(
                        tenant_id=str(job.tenant_id),
                        pipeline_id=str(job.executable_pipeline_id),
                        job_id=str(job.id),
                        step_id=step_id,
                        config=config,
                        db=self.db
                    )

                    # Execute
                    op_input = OperatorInput(data=input_data, metadata=input_metadata)
                    output = await executor.safe_execute(op_input, context)
                    
                    results[step_id] = output
                    
                    # Update Step Status
                    if step_exec:
                        step_exec.completed_at = datetime.utcnow()
                        step_exec.metadata_ = output.metadata
                        
                        try:
                            step_exec.output_data = output.data
                        except Exception:
                            step_exec.output_data = {"error": "Could not serialize output"}

                        if output.success:
                            step_exec.status = PipelineStepStatus.COMPLETED
                        else:
                            step_exec.status = PipelineStepStatus.FAILED
                            step_exec.error_message = output.error_message
                        
                        await self.db.commit()

                    if not output.success:
                        raise Exception(f"Step {step_id} ({op_id}) failed: {output.error_message}")

                    # If this is an OUTPUT node (retrieval result) or STORAGE node, capture its output
                    if spec.category == OperatorCategory.OUTPUT:
                        job.output = output.data
                    elif spec.category == OperatorCategory.STORAGE:
                        # For storage nodes, we might want to capture metadata or counts
                        if job.output is None:
                            job.output = {}
                        if isinstance(job.output, dict):
                            job.output[step_id] = output.data

                except Exception as step_err:
                    if step_exec:
                        step_exec.status = PipelineStepStatus.FAILED
                        step_exec.error_message = str(step_err)
                        step_exec.completed_at = datetime.utcnow()
                        await self.db.commit()
                    raise step_err

            # 6. Success
            job.status = PipelineJobStatus.COMPLETED
            job.completed_at = datetime.utcnow()
            await self.db.commit()

        except Exception as e:
            # Log full traceback
            print(f"Pipeline execution failed: {str(e)}")
            traceback.print_exc()
            
            # Re-fetch job to ensure attached to session (if error happened during commit)
            # But session might be invalid if commit failed. 
            # We assume session is still usable for a rollback/new transaction or just a new update
            try:
                job.status = PipelineJobStatus.FAILED
                job.error_message = str(e)
                job.completed_at = datetime.utcnow()
                await self.db.commit()
            except Exception as e2:
                print(f"Failed to update job status: {e2}")

