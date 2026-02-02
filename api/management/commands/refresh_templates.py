from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from api.models import FileStructureMetadata
from processors.template_learner import TemplateLearner

class Command(BaseCommand):
    help = 'Iterates through all FileStructure objects and runs the TemplateLearner to refine the blacklists.'

    def handle(self, *args, **options):
        # We might need a user to instantiate TemplateLearner
        # Since TemplateLearner is mostly used per-user, but FileStructureMetadata is global-ish (by row_hash),
        # we can pick a superuser or the first user as a representative, 
        # or we might need to adjust TemplateLearner if it should be truly global.
        # Based on requirements, TemplateLearner accepts a User.
        
        user = User.objects.filter(is_superuser=True).first() or User.objects.first()
        if not user:
            self.stdout.write(self.style.ERROR('No user found in the system.'))
            return

        structures = FileStructureMetadata.objects.all()
        self.stdout.write(f"Refreshing templates for {structures.count()} structures...")

        for structure in structures:
            self.stdout.write(f"Processing structure {structure.row_hash}...")
            learner = TemplateLearner(user, structure)
            new_blacklist = learner.find_template_words()
            
            # Update if we found something or if we want to keep it in sync
            structure.template_blacklist = new_blacklist
            structure.save()
            self.stdout.write(self.style.SUCCESS(f"Successfully updated blacklist for {structure.row_hash}"))

        self.stdout.write(self.style.SUCCESS('Finished refreshing all templates.'))
