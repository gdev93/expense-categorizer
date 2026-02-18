from django.http import HttpResponseRedirect

class HTMXRedirectMiddleware:
    """
    Middleware that handles HTMX redirects.
    If a request is made via HTMX and the response is a redirect (302),
    it adds the 'HX-Redirect' header so HTMX can perform a full page redirect.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if 'HX-Request' in request.headers:
            if response.status_code == 302:
                # Get the redirect URL
                redirect_url = response['Location']
                # Create a new response with HX-Redirect header
                # We change status to 200 so the browser doesn't follow the redirect automatically
                # and htmx can handle the HX-Redirect header.
                response['HX-Redirect'] = redirect_url
                response.status_code = 200
            
            # Handle possible errors when we want to ensure we only swap the content
            # and not the whole page if something goes wrong.
            # But hx-select in the template handles this.

        return response
