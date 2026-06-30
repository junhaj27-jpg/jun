"""Django/DRF 연결 예시입니다. 실제 프로젝트에서는 GPU Worker에서 service.warmup()을 1회 실행하세요."""

from rest_framework.response import Response
from rest_framework.views import APIView

from requirements_gold_agent import RequirementsGenerationService


service = RequirementsGenerationService.get_instance()


class RequirementGoldGenerateView(APIView):
    def post(self, request):
        result = service.generate_from_dict(
            request.data,
            job_id=request.data.get("document_id"),
        )
        return Response({
            "document_id": result["document_id"],
            "gold_requirement_count": result["gold_requirement_count"],
            "quality": result["quality"],
            "gold_requirement_specification": result["gold_requirement_specification"],
        })
