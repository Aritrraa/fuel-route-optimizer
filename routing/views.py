import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .services import optimizer, planner, routing_client


def index(request):
    return render(request, "routing/index.html")


def _parse_float(val, name, min_val, max_val):
    if val is None or val == "":
        return None
    try:
        f = float(val)
    except (ValueError, TypeError):
        raise ValueError(f"'{name}' must be a valid number")
    if not (min_val <= f <= max_val):
        raise ValueError(f"'{name}' must be between {min_val} and {max_val}")
    return f


@csrf_exempt
@require_http_methods(["GET", "POST"])
def route_api(request):
    if request.method == "POST":
        try:
            body = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON body"}, status=400)
        start, finish = body.get("start"), body.get("finish")
        raw_range = body.get("range_miles") if "range_miles" in body else body.get("range")
        raw_mpg = body.get("mpg")
        raw_corridor = body.get("corridor_miles") if "corridor_miles" in body else body.get("corridor")
    else:
        start, finish = request.GET.get("start"), request.GET.get("finish")
        raw_range = request.GET.get("range_miles") or request.GET.get("range")
        raw_mpg = request.GET.get("mpg")
        raw_corridor = request.GET.get("corridor_miles") or request.GET.get("corridor")

    if not start or not finish:
        return JsonResponse({"error": "Both 'start' and 'finish' are required"}, status=400)

    try:
        range_miles = _parse_float(raw_range, "range_miles", 50, 1500)
        mpg = _parse_float(raw_mpg, "mpg", 1, 60)
        corridor_miles = _parse_float(raw_corridor, "corridor_miles", 0.5, 30)
        return JsonResponse(planner.build_plan(start, finish, range_miles, mpg, corridor_miles))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except optimizer.InfeasibleRoute as exc:
        return JsonResponse({"error": str(exc)}, status=422)
    except routing_client.RoutingError as exc:
        return JsonResponse({"error": str(exc)}, status=502)
