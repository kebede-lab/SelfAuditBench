import os
import logging

from openai import AzureOpenAI, OpenAI

try:
    import torch
    from transformers import AutoTokenizer, pipeline, AutoModelForCausalLM, AutoConfig
    HAS_LOCAL_HF = True
except ImportError:
    torch = None
    AutoTokenizer = pipeline = AutoModelForCausalLM = AutoConfig = None
    HAS_LOCAL_HF = False

try:
    from azure.identity import AzureCliCredential, get_bearer_token_provider
    from azure.core.credentials import AzureKeyCredential
    from langchain_openai import AzureChatOpenAI
    HAS_AZURE_OPENAI = True
except ImportError:
    AzureCliCredential = get_bearer_token_provider = AzureKeyCredential = AzureChatOpenAI = None
    HAS_AZURE_OPENAI = False

# Optional import for Azure AI Inference
try:
    from azure.ai.inference import ChatCompletionsClient
    HAS_AZURE_AI_INFERENCE = True
except ImportError:
    HAS_AZURE_AI_INFERENCE = False
    ChatCompletionsClient = None

# Optional import for Anthropic
try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False
    anthropic = None

# Optional import for Anthropic Vertex AI
try:
    from anthropic import AnthropicVertex
    HAS_ANTHROPIC_VERTEX = True
except ImportError:
    HAS_ANTHROPIC_VERTEX = False
    AnthropicVertex = None

# Optional import for Google Generative AI
try:
    from google import genai
    from google.genai import types
    HAS_GOOGLE_AI = True
except ImportError:
    HAS_GOOGLE_AI = False
    genai = None
    types = None

logger = logging.getLogger(__name__)


class LLM:
    def __init__(self, llm_name: str, config: dict):
        """
        Unified LLM class that supports Azure models, OpenAI API, Anthropic/Claude, Google/Gemini, and HuggingFace models.
        
        Args:
            llm_name: Name of the model
            config: Configuration dictionary with provider and model settings
            
        Config options:
            provider: "azure", "openai", "anthropic", "anthropic_vertex", "google", or "huggingface"
            azure_endpoint: Azure endpoint URL (for Azure provider)
            use_azure_credentials: bool, if True uses DefaultAzureCredential (for Azure)
            max_new_tokens: Maximum new tokens to generate
            top_p: Top-p sampling parameter
            temperature: Temperature for sampling
            
        Environment Variables Required:
            - Azure: AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY (if not using credentials)
            - OpenAI: OPENAI_API_KEY
            - Anthropic: ANTHROPIC_API_KEY
            - Anthropic Vertex: GOOGLE_CLOUD_PROJECT_ID, GOOGLE_CLOUD_REGION (optional)
            - Google: GOOGLE_AI_API_KEY
        """
        self.llm_name = llm_name
        self.config = config
        
        # Get provider from config or infer from model name and config
        provider = self._determine_provider()
        
        if provider == "azure":
            self.llm = AzureLLM(self.llm_name, self.config)
        elif provider == "openai":
            self.llm = OpenAILLM(self.llm_name, self.config)
        elif provider == "anthropic":
            self.llm = AnthropicLLM(self.llm_name, self.config)
        elif provider == "anthropic_vertex":
            self.llm = AnthropicVertexLLM(self.llm_name, self.config)
        elif provider == "google":
            self.llm = GoogleLLM(self.llm_name, self.config)
        elif provider == "huggingface":
            self.llm = HuggingFaceLLM(self.llm_name, self.config)
        else:
            raise ValueError(f"Unsupported provider: {provider}")
    
    def _determine_provider(self) -> str:
        """Determine the provider based on config and model name"""
        # Explicit provider in config takes precedence
        if hasattr(self.config, 'provider'):
            return self.config.provider
        if isinstance(self.config, dict) and 'provider' in self.config:
            return self.config['provider']
            
        # Legacy config support
        if hasattr(self.config, 'local_llm') and self.config.local_llm:
            return "huggingface"
        if isinstance(self.config, dict) and self.config.get('local_llm', False):
            return "huggingface"
            
        if hasattr(self.config, 'azure') and self.config.azure:
            return "azure"
        if isinstance(self.config, dict) and self.config.get('azure', False):
            return "azure"
            
        if hasattr(self.config, 'openai') and self.config.openai:
            return "openai"
        if isinstance(self.config, dict) and self.config.get('openai', False):
            return "openai"
            
        if hasattr(self.config, 'anthropic') and self.config.anthropic:
            return "anthropic"
        if isinstance(self.config, dict) and self.config.get('anthropic', False):
            return "anthropic"
            
        if hasattr(self.config, 'anthropic_vertex') and self.config.anthropic_vertex:
            return "anthropic_vertex"
        if isinstance(self.config, dict) and self.config.get('anthropic_vertex', False):
            return "anthropic_vertex"
            
        if hasattr(self.config, 'google') and self.config.google:
            return "google"
        if isinstance(self.config, dict) and self.config.get('google', False):
            return "google"
        
        # Default inference based on model name
        if "gpt" in self.llm_name.lower() or "deepseek" in self.llm_name.lower():
            # Check if we have Azure endpoint configured
            if (hasattr(self.config, 'azure_endpoint') or 
                (isinstance(self.config, dict) and 'azure_endpoint' in self.config) or
                os.getenv("AZURE_OPENAI_ENDPOINT")):
                return "azure"
            else:
                return "openai"
        elif "claude" in self.llm_name.lower():
            return "anthropic"
        elif "gemini" in self.llm_name.lower():
            return "google"
        else:
            return "huggingface"

    def call_model(self, messages: list) -> str:
        """Calls the LLM model with the given messages.

        Returns:
            str: The response from the LLM.
        """
        return self.llm.call_model(messages)



class AzureLLM:
    """Azure LLM model with support for both API key and DefaultAzureCredential authentication."""

    def __init__(self, llm_name: str, config: dict):
        self.llm_name = llm_name
        self.max_new_tokens = self._get_config_value(config, 'max_new_tokens', 3000)
        self.top_p = self._get_config_value(config, 'llm_top_p', 1.0)
        self.temperature = self._get_config_value(config, 'temperature', 0.7)
        
        # Determine if this is Azure OpenAI or Azure AI Inference
        azure_endpoint = self._get_config_value(config, 'azure_endpoint') or os.getenv("AZURE_OPENAI_ENDPOINT")
        use_azure_credentials = self._get_config_value(config, 'use_azure_credentials', True)
        
        if not azure_endpoint:
            raise ValueError("Azure endpoint must be provided via config['azure_endpoint'] or AZURE_OPENAI_ENDPOINT environment variable")
        
        # Check if this is Azure OpenAI (for GPT models) or Azure AI Inference
        if "gpt" in self.llm_name.lower() or "openai" in azure_endpoint.lower():
            self._setup_azure_openai(azure_endpoint, use_azure_credentials)
        else:
            self._setup_azure_ai_inference(azure_endpoint, use_azure_credentials, model_name=self.llm_name, temperature=self.temperature)
    
    def _get_config_value(self, config, key, default=None):
        """Get value from config dict or object"""
        if isinstance(config, dict):
            return config.get(key, default)
        else:
            return getattr(config, key, default)
    
    def _setup_azure_openai(self, azure_endpoint: str, use_azure_credentials: bool):
        """Setup Azure OpenAI client"""
        try:
            if use_azure_credentials:
                # Use AzureCliCredential (requires 'az login')
                credential = AzureCliCredential()
                self.client = AzureOpenAI(
                    azure_endpoint=azure_endpoint,
                    azure_ad_token_provider=lambda: credential.get_token("https://cognitiveservices.azure.com/.default").token,
                    api_version="2024-02-15-preview",
                )
                self.client_type = "azure_openai_credential"
            else:
                # Use API key
                api_key = os.getenv("AZURE_OPENAI_API_KEY")
                if not api_key:
                    raise ValueError("AZURE_OPENAI_API_KEY environment variable is required when use_azure_credentials=False")
                
                self.client = AzureOpenAI(
                    azure_endpoint=azure_endpoint,
                    api_key=api_key,
                    api_version="2024-02-15-preview",
                )
                self.client_type = "azure_openai_key"
                
            logger.info(f"Initialized Azure OpenAI client with {self.client_type}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Azure OpenAI client: {e}")
            raise
    
    def _setup_azure_ai_inference(self, azure_endpoint: str, use_azure_credentials: bool, model_name:str, api_version:str = "2025-01-01-preview", max_tokens:int=3000, temperature:float=1.0):
        """Setup Azure AI Inference client"""
        if not HAS_AZURE_AI_INFERENCE:
            raise ImportError("azure-ai-inference package is required for Azure AI Inference. Install with: pip install azure-ai-inference")
        
        try:
            if use_azure_credentials:
                # Use AzureCliCredential (requires 'az login')
                credential = AzureCliCredential()
                # For ChatCompletionsClient, we need to get the token
                token =  get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")
                self.client = AzureChatOpenAI(
                    deployment_name=model_name,
                    api_version=api_version,
                    azure_endpoint=azure_endpoint,
                    azure_ad_token_provider=token,
                    max_tokens=max_tokens,
                    temperature = temperature
                )
                self.client_type = "azure_ai_credential_vllm"
            else:
                raise NotImplementedError
                
            logger.info(f"Initialized Azure AI Inference client with {self.client_type}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Azure AI Inference client: {e}")
            raise

    def call_model(self, messages: list) -> str:
        """Call the Azure model with the given messages."""
        try:
            if self.client_type.startswith("azure_openai"):
                # Azure OpenAI API
                response = self.client.chat.completions.create(
                    model=self.llm_name,
                    messages=messages,
                    top_p=self.top_p,
                    temperature=self.temperature,
                    max_tokens=self.max_new_tokens,
                )
                return response.choices[0].message.content
                
            elif self.client_type.startswith("azure_ai_credential_vllm"):
                # Azure AI Inference API
                response = self.client.invoke(messages)
                return response.content
                
        except Exception as e:
            logger.error(f"Error calling Azure model {self.llm_name}: {e}")
            raise


class OpenAILLM:
    """OpenAI LLM model using OpenAI API directly."""

    def __init__(self, llm_name: str, config: dict):
        self.llm_name = llm_name
        self.max_new_tokens = self._get_config_value(config, 'max_new_tokens', 1000)
        self.top_p = self._get_config_value(config, 'llm_top_p', 1.0)
        self.temperature = self._get_config_value(config, 'temperature', 0.7)

        # Get OpenAI-compatible API key and optional base URL.
        # This supports OpenAI itself plus cheaper OpenAI-compatible providers such as DeepSeek.
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required for OpenAI-compatible provider")

        base_url = os.getenv("BASE_URL") or os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE")
        if base_url:
            self.client = OpenAI(api_key=api_key, base_url=base_url)
            logger.info(f"Initialized OpenAI-compatible client with base_url={base_url}")
        else:
            self.client = OpenAI(api_key=api_key)
            logger.info("Initialized OpenAI client")

    def _get_config_value(self, config, key, default=None):
        """Get value from config dict or object"""
        if isinstance(config, dict):
            return config.get(key, default)
        else:
            return getattr(config, key, default)

    def call_model(self, messages: list) -> str:
        """Call the OpenAI model with the given messages."""
        try:
            # Handle GPT-5 models vs older models
            if self.llm_name.startswith("gpt-5"):
                response = self.client.chat.completions.create(
                    model=self.llm_name,
                    messages=messages,
                    top_p=self.top_p,
                    max_completion_tokens=self.max_new_tokens,  # Changed from max_tokens
                    # Some OpenAI-compatible providers reject "minimal" and accept only
                    # high/low/medium/max/xhigh. "low" is the most portable low-cost
                    # setting for GPT-5-style reasoning models.
                    reasoning_effort="low",
                )
            elif self.llm_name.startswith("o"):
                response = self.client.chat.completions.create(
                    model=self.llm_name,
                    messages=messages,
                    top_p=self.top_p,
                    max_completion_tokens=self.max_new_tokens,  # Changed from max_tokens
                    reasoning_effort="low",  # Add this to minimize reasoning
                )
            else:
                provider_options = {"stream": False}
                if self.llm_name.startswith("deepseek-v4"):
                    # DeepSeek V4 defaults to high-effort thinking. ConVerse expects
                    # ordinary formatted chat content and does not consume
                    # reasoning_content, so keep this reproduction in non-thinking
                    # mode and avoid proxy stream timeouts before content is emitted.
                    provider_options["extra_body"] = {
                        "thinking": {"type": "disabled"}
                    }
                response = self.client.chat.completions.create(
                    model=self.llm_name,
                    messages=messages,
                    top_p=self.top_p,
                    temperature=self.temperature,
                    max_tokens=self.max_new_tokens,  # Keep original for older models
                    **provider_options,
                )

            content = response.choices[0].message.content
            # Handle potential encoding issues
            if content:
                return content.encode('utf-8', errors='ignore').decode('utf-8')
            return ""

        except Exception as e:
            logger.error(f"Error calling OpenAI model {self.llm_name}: {e}")
            raise


class AnthropicLLM:
    """Anthropic LLM model using Claude API."""

    def __init__(self, llm_name: str, config: dict):
        if not HAS_ANTHROPIC:
            raise ImportError("anthropic package is required for Anthropic provider. Install with: pip install anthropic")
        
        self.llm_name = llm_name
        self.max_tokens = self._get_config_value(config, 'max_new_tokens', 3000)
        self.top_p = self._get_config_value(config, 'llm_top_p', 1.0)
        self.temperature = self._get_config_value(config, 'temperature', 0.7)

        # Get Anthropic API key
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required for Anthropic provider")

        self.client = anthropic.Anthropic(api_key=api_key)
        logger.info("Initialized Anthropic client")

    def _get_config_value(self, config, key, default=None):
        """Get value from config dict or object"""
        if isinstance(config, dict):
            return config.get(key, default)
        else:
            return getattr(config, key, default)

    def call_model(self, messages: list) -> str:
        """Call the Anthropic model with the given messages."""
        try:
            # Extract system messages and combine them
            system_content = ""
            non_system_messages = []
            
            for msg in messages:
                if msg.get('role') == 'system':
                    content = msg.get('content', '').strip()
                    if content:
                        if system_content:
                            system_content += "\n\n" + content
                        else:
                            system_content = content
                else:
                    non_system_messages.append(msg)
            
            # Ensure we have at least one non-system message
            if not non_system_messages:
                non_system_messages = [{"role": "user", "content": "Please continue."}]
            
            # Create request parameters
            params = {
                "model": self.llm_name,
                "messages": non_system_messages,
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
                "top_p": self.top_p,
            }
            
            # Add system parameter if we have system content
            if system_content:
                params["system"] = system_content
            
            response = self.client.messages.create(**params)
            
            content = response.content[0].text if response.content else ""
            # Handle potential encoding issues
            if content:
                return content.encode('utf-8', errors='ignore').decode('utf-8')
            return ""

        except Exception as e:
            logger.error(f"Error calling Anthropic model {self.llm_name}: {e}")
            raise


class AnthropicVertexLLM:
    """Anthropic Claude model using AnthropicVertex SDK on Google Cloud Vertex AI."""

    def __init__(self, llm_name: str, config: dict):
        if not HAS_ANTHROPIC_VERTEX:
            raise ImportError(
                "The 'anthropic' package with Vertex AI support is required for Anthropic Vertex provider. "
                "Install with: pip install 'anthropic[vertex]'"
            )
        
        self.llm_name = llm_name
        self.max_tokens = self._get_config_value(config, 'max_new_tokens', 3000)
        self.temperature = self._get_config_value(config, 'temperature', 0.7)
        self.top_p = self._get_config_value(config, 'llm_top_p', 1.0)

        # Vertex AI project ID and region are needed for AnthropicVertex client
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT_ID")
        self.region = self._get_config_value(config, 'google_cloud_region') or os.getenv("GOOGLE_CLOUD_REGION", "us-central1")
        
        if not self.project_id:
            raise ValueError(
                "GOOGLE_CLOUD_PROJECT_ID environment variable is required for AnthropicVertex provider. "
                "Ensure you have authenticated to Google Cloud (e.g., `gcloud auth application-default login`)."
            )

        self.client = AnthropicVertex(
            project_id=self.project_id,
            region=self.region
        )
        logger.info(f"Initialized AnthropicVertex client for project {self.project_id} in {self.region}")

    def _get_config_value(self, config, key, default=None):
        """Get value from config dict or object"""
        if isinstance(config, dict):
            return config.get(key, default)
        else:
            return getattr(config, key, default)

    def call_model(self, messages: list) -> str:
        """Call the Anthropic Claude model on Vertex AI with the given messages."""
        try:
            # Extract system messages and combine them
            system_content = ""
            non_system_messages = []
            
            for msg in messages:
                if msg.get('role') == 'system':
                    content = msg.get('content', '').strip()
                    if content:
                        if system_content:
                            system_content += "\n\n" + content
                        else:
                            system_content = content
                else:
                    non_system_messages.append(msg)
            
            # Ensure we have at least one non-system message
            if not non_system_messages:
                non_system_messages = [{"role": "user", "content": "Please continue."}]
            
            # Create request parameters
            params = {
                "model": self.llm_name,
                "messages": non_system_messages,
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
                "top_p": self.top_p,
            }
            
            # Add system parameter if we have system content
            if system_content:
                params["system"] = system_content
            
            response = self.client.messages.create(**params)
            
            # Extract text from response content blocks
            content = ""
            for content_block in response.content:
                if content_block.type == "text":
                    content += content_block.text
            
            # Handle potential encoding issues
            if content:
                return content.encode('utf-8', errors='ignore').decode('utf-8')
            return ""

        except Exception as e:
            logger.error(f"Error calling Anthropic Vertex model {self.llm_name}: {e}")
            raise


class GoogleLLM:
    """Google Generative AI model using Gemini API with google-genai package."""

    def __init__(self, llm_name: str, config: dict):
        if not HAS_GOOGLE_AI:
            raise ImportError("google-genai package is required for Google provider. Install with: pip install google-genai")
        
        self.llm_name = llm_name
        self.max_output_tokens = self._get_config_value(config, 'max_new_tokens', 3000)
        self.top_p = self._get_config_value(config, 'llm_top_p', 1.0)
        self.temperature = self._get_config_value(config, 'temperature', 0.7)

        # Get Google AI API key
        api_key = os.getenv("GOOGLE_AI_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_AI_API_KEY environment variable is required for Google provider")

        self.client = genai.Client(api_key=api_key)
        logger.info("Initialized Google Generative AI client")

    def _get_config_value(self, config, key, default=None):
        """Get value from config dict or object"""
        if isinstance(config, dict):
            return config.get(key, default)
        else:
            return getattr(config, key, default)

    def call_model(self, messages: list) -> str:
        """Call the Google Gemini model with the given messages."""
        try:
            # Extract system messages and combine them
            system_parts = []
            contents = []
            
            for msg in messages:
                role = msg.get('role')
                content = msg.get('content', '').strip()
                
                if role == 'system' and content:
                    system_parts.append(types.Part.from_text(text=content))
                elif role in ['user', 'assistant'] and content:
                    # Map assistant to model for Google's format
                    google_role = 'model' if role == 'assistant' else 'user'
                    contents.append(types.Content(
                        role=google_role,
                        parts=[types.Part.from_text(text=content)]
                    ))
            
            # If no user/assistant messages, create a default user message
            if not contents:
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part.from_text(text="Please respond appropriately.")]
                ))
            
            # Create generation config
            config_params = {
                "max_output_tokens": self.max_output_tokens,
                "temperature": self.temperature,
                "top_p": self.top_p,
            }
            
            # Add system instruction if we have system parts
            if system_parts:
                config_params["system_instruction"] = system_parts
            
            generate_content_config = types.GenerateContentConfig(**config_params)
            
            # Generate response
            response = self.client.models.generate_content(
                model=self.llm_name,
                contents=contents,
                config=generate_content_config,
            )
            
            content = response.text if hasattr(response, 'text') else ""
            # Handle potential encoding issues
            if content:
                return content.encode('utf-8', errors='ignore').decode('utf-8')
            return ""

        except Exception as e:
            logger.error(f"Error calling Google model {self.llm_name}: {e}")
            raise


class HuggingFaceLLM:
    """HuggingFace model for local inference."""

    def __init__(self, llm_name: str, config: dict):
        if not HAS_LOCAL_HF:
            raise ImportError("torch and transformers are required for HuggingFace/local inference. The DeepSeek reproduction uses --provider openai and does not need them.")
        self.llm_name = llm_name
        self.max_new_tokens = self._get_config_value(config, 'max_new_tokens', 1000)
        self.top_p = self._get_config_value(config, 'llm_top_p', 1.0)
        self.temperature = self._get_config_value(config, 'temperature', 0.7)
        
        # Optional cache directory
        self.cache_dir = self._get_config_value(config, 'cache_dir', '')
        
        # Setup HuggingFace model
        self.hf_model, self.hf_tokenizer, self.hf_pipeline = self._setup_hf_model()
        logger.info(f"Initialized HuggingFace model: {self.llm_name}")
    
    def _get_config_value(self, config, key, default=None):
        """Get value from config dict or object"""
        if isinstance(config, dict):
            return config.get(key, default)
        else:
            return getattr(config, key, default)

    def _setup_hf_model(self):
        """Setup HuggingFace model, tokenizer, and pipeline."""
        try:
            # Load configuration
            config = AutoConfig.from_pretrained(
                self.llm_name,
                use_cache=True,
                cache_dir=os.path.join(self.cache_dir, self.llm_name) if self.cache_dir else None,
                device_map="auto",
                trust_remote_code=True,
            )
            
            # Load model
            model = AutoModelForCausalLM.from_pretrained(
                self.llm_name,
                config=config,
                cache_dir=os.path.join(self.cache_dir, self.llm_name) if self.cache_dir else None,
                device_map="auto",
                torch_dtype=torch.float16,  # Use float16 for efficiency
                trust_remote_code=True,
            )
            model.eval()
            
            # Load tokenizer
            tokenizer = AutoTokenizer.from_pretrained(
                self.llm_name, 
                use_cache=True,
                cache_dir=os.path.join(self.cache_dir, self.llm_name) if self.cache_dir else None,
                trust_remote_code=True,
            )
            
            # Set pad token if not present
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token
            
            # Create pipeline
            pipeline_gen = pipeline(
                "text-generation",
                model=model,
                tokenizer=tokenizer,
                max_new_tokens=self.max_new_tokens,
                return_full_text=False,
                device_map="auto",
            )
            
            return model, tokenizer, pipeline_gen
            
        except Exception as e:
            logger.error(f"Failed to setup HuggingFace model {self.llm_name}: {e}")
            raise

    def call_model(self, messages: list) -> str:
        """Call the HuggingFace model with the given messages."""
        try:
            # Apply chat template if available
            if hasattr(self.hf_tokenizer, 'apply_chat_template'):
                model_input = self.hf_tokenizer.apply_chat_template(
                    messages, 
                    tokenize=False, 
                    add_generation_prompt=True
                )
            else:
                # Fallback: simple concatenation
                model_input = ""
                for msg in messages:
                    role = msg.get('role', 'user')
                    content = msg.get('content', '')
                    model_input += f"{role}: {content}\n"
                model_input += "assistant: "
            
            # Generate response
            output = self.hf_pipeline(
                model_input,
                do_sample=True,
                top_p=self.top_p,
                temperature=self.temperature,
                max_new_tokens=self.max_new_tokens,
                pad_token_id=self.hf_tokenizer.eos_token_id,
            )
            
            return output[0]["generated_text"].strip()
            
        except Exception as e:
            logger.error(f"Error calling HuggingFace model {self.llm_name}: {e}")
            raise


# Legacy compatibility classes (deprecated)
class LocalOpenLLM(HuggingFaceLLM):
    """Legacy alias for HuggingFaceLLM"""
    def __init__(self, llm_name: str, config: dict):
        logger.warning("LocalOpenLLM is deprecated. Use HuggingFaceLLM instead.")
        super().__init__(llm_name, config)


class GPTLLM(AzureLLM):
    """Legacy alias for AzureLLM with Azure OpenAI"""
    def __init__(self, llm_name: str, config: dict):
        logger.warning("GPTLLM is deprecated. Use AzureLLM instead.")
        # Force Azure OpenAI setup
        if isinstance(config, dict):
            config['azure_endpoint'] = config.get('azure_endpoint') or os.getenv("AZURE_OPENAI_ENDPOINT")
        super().__init__(llm_name, config)


class GPTLLMOpenAI(OpenAILLM):
    """Legacy alias for OpenAILLM"""
    def __init__(self, llm_name: str, config: dict):
        logger.warning("GPTLLMOpenAI is deprecated. Use OpenAILLM instead.")
        super().__init__(llm_name, config)
