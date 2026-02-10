import logging
from celery import shared_task
from google import genai
from agent.agent import call_gemini_api, GeminiResponse, get_api_key

logger = logging.getLogger(__name__)

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={'max_retries': 5},
    name='api.tasks.call_gemini_with_retry'
)
def call_gemini_with_retry(self, prompt: str, temperature: float = 0.1):
    """
    Celery task to call Gemini API with automatic retries on failure.
    """
    try:
        api_key = get_api_key()
        client = genai.Client(api_key=api_key)
        
        response = call_gemini_api(prompt, client, temperature)
        
        # We return a dict because GeminiResponse (dataclass) might not be JSON serializable 
        # by default in some celery configurations if not handled, 
        # but here we just want to show the scaffolding.
        return {
            'text': response.text,
            'prompt_tokens': response.prompt_tokens,
            'candidate_tokens': response.candidate_tokens,
            'model_name': response.model_name
        }
    except Exception as exc:
        logger.error(f"Error calling Gemini API: {exc}")
        # Re-raise to trigger autoretry_for
        raise exc
