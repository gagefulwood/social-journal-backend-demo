from collections import Counter
from datetime import date, datetime, time, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q, Value
from django.db.models.functions import Concat
from django.utils import timezone

from contacts.models import Contact, ContactAddress, ContactEducation, ContactEmployment, ContactMethod, Fact, Observation
from events.models import Event, EventParticipant
from journals.models import EmotionalManifestation, EmotionalReflectionDetail, EpisodeLogDetail, FreeReflectionDetail, InteractionReflectionDetail, Log, MomentReflectionDetail, Reflection, ReflectionAttachment, ReflectionContact, SentimentLogDetail, SocialEnergyLogDetail
from lookups.models import ContextCategory, EmotionState, EpisodeCategory, EpisodeCharacteristic, EpisodeContextTag, FactCategory, InteractionDynamic, InteractionMode, Mood, ObservationMarker, Relation, SocialEnergyFactor
from media.models import MediaAsset
from users.models import Users

CONTACTS = (
("Alex","Rivera","alex.rivera@example.com","+1-555-0101","Friend","Northstar Studio","He/him","America/Chicago","Product designer","Computer Science"),
("Jordan","Lee","jordan.lee.demo@example.com","+1-555-0102","Coworker","Acme Labs","They/them","America/New_York","Program manager","Communications"),
("Priya","Shah","priya.shah.demo@example.com","+1-555-0103","Friend","Civic Works","She/her","America/Chicago","Community planner","Public Policy"),
("Marcus","Chen","marcus.chen.demo@example.com","+1-555-0104","Mentor","Chen Advisory","He/him","America/Chicago","Independent advisor","Business"),
("Elena","Torres","elena.torres.demo@example.com","+1-555-0105","Family","Jackson Family Center","She/her","America/Chicago","Community coordinator","Nutrition"),
("Sam","Bennett","sam.bennett.demo@example.com","+1-555-0106","Friend","Greenway Books","They/them","America/Chicago","Bookseller","English"),
("Maya","Patel","maya.patel.demo@example.com","+1-555-0107","Coworker","Acme Labs","She/her","America/New_York","Research lead","Human-Computer Interaction"),
("Theo","Morgan","theo.morgan.demo@example.com","+1-555-0108","Family","Morgan Repairs","He/him","America/Chicago","Owner","Automotive Technology"),
)
EVENTS = (
("Coffee catch-up with Alex",0,(0,),"Social","In person","Happy","Corner Coffee","positive"),
("Team lunch with Jordan",-2,(1,6),"Professional","In person","Neutral","Market Hall","neutral"),
("Weekend hike with Priya",-4,(2,5),"Social","In person","Happy","Cedar Ridge Trail","positive"),
("Career advice call with Marcus",-7,(3,),"Professional","Phone call","Neutral","","positive"),
("Family dinner with Elena",-9,(4,7),"Family","In person","Happy","Elena's home","positive"),
("Video catch-up with Alex",-12,(0,),"Social","Video call","Neutral","","neutral"),
("Planning session with Jordan",-15,(1,),"Professional","Video call","Neutral","","positive"),
("Garden volunteer morning with Priya",-18,(2,5),"Social","In person","Happy","Community Garden","positive"),
("Book discussion with Marcus",-21,(3,),"Professional","Video call","Happy","","positive"),
("Recipe swap with Elena",-24,(4,),"Family","Phone call","Happy","","positive"),
("Bookstore browse with Sam",-27,(5,),"Social","In person","Happy","Greenway Books","positive"),
("Research review with Maya",-30,(6,1),"Professional","Video call","Neutral","","positive"),
("Family call with Theo",-33,(7,),"Family","Phone call","Happy","","positive"),
("Friends game night",-36,(0,2,5),"Social","In person","Happy","Alex's apartment","positive"),
("Park walk with Sam",-38,(5,),"Social","In person","Neutral","Riverside Park","positive"),
("Design workshop with Maya",-40,(6,1),"Professional","In person","Neutral","Acme Labs","positive"),
("Garage afternoon with Theo",-42,(7,4),"Family","In person","Happy","Morgan Repairs","positive"),
("Coffee before work with Alex",-44,(0,),"Social","In person","Happy","Corner Coffee","positive"),
("Project retrospective with Jordan",-46,(1,6),"Professional","Video call","Neutral","","neutral"),
("Trail planning call with Priya",-48,(2,),"Social","Phone call","Happy","","positive"),
("Mentor office hours with Marcus",-50,(3,),"Professional","Video call","Neutral","","positive"),
("Sunday lunch with Elena",-52,(4,7),"Family","In person","Happy","Magnolia Kitchen","positive"),
("Poetry reading with Sam",-54,(5,2),"Social","In person","Happy","Greenway Books","positive"),
("Interview debrief with Maya",-55,(6,),"Professional","Video call","Neutral","","positive"),
("Parts pickup with Theo",-56,(7,),"Social","In person","Neutral","Morgan Repairs","neutral"),
("Neighborhood picnic",-57,(0,5,2),"Social","In person","Happy","Riverside Park","positive"),
("Quarterly planning group",-58,(1,6,3),"Professional","Video call","Neutral","","positive"),
("Family photo sorting",-59,(4,7),"Family","In person","Happy","Elena's home","positive"),
)
COMPLETED = ("episode","social_energy","sentiment","interaction","moment","emotional","free","sentiment","episode","social_energy","sentiment","interaction","moment","sentiment","emotional","episode","social_energy","interaction","moment","sentiment","free")
DRAFTS = ("episode","social_energy","sentiment","interaction","moment","emotional","free")

class Command(BaseCommand):
    help = "Preview or reset deterministic demo-domain data for an existing account."

    def add_arguments(self, parser):
        parser.add_argument("user_name")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--reset-demo-data", action="store_true")
        parser.add_argument("--confirm-reset", action="store_true")
        parser.add_argument("--anchor-date")

    def handle(self, *args, **options):
        user = self._user(options["user_name"])
        reset, confirm = options["reset_demo_data"], options["confirm_reset"]
        if reset != confirm:
            raise CommandError("A real reset requires both --reset-demo-data and --confirm-reset.")
        if options["dry_run"] and reset:
            raise CommandError("Choose either --dry-run or the confirmed reset flags, not both.")
        anchor = self._anchor(options.get("anchor_date"))
        dry_run = not reset
        with transaction.atomic():
            deleted = self._delete(user)
            created = self._populate(user, anchor)
            if dry_run:
                transaction.set_rollback(True)
        dv, cv = ("Would delete","would create") if dry_run else ("Deleted","created")
        self.stdout.write(self.style.SUCCESS(f"{dv} {self._summary(deleted)}; {cv} {self._summary(created)} for {user.username} ({user.email}), anchored on {anchor}."))

    def _user(self, selector):
        selector = " ".join(selector.split())
        qs = Users.objects.annotate(full_name=Concat("first_name",Value(" "),"last_name")).filter(Q(username__iexact=selector)|Q(email__iexact=selector)|Q(full_name__iexact=selector))
        users = list(qs.order_by("id")[:2])
        if not users: raise CommandError(f'No user matched "{selector}".')
        if len(users)>1: raise CommandError(f'More than one user matched "{selector}".')
        return users[0]

    def _anchor(self, value):
        if not value: return timezone.localdate()
        try: return date.fromisoformat(value)
        except ValueError as exc: raise CommandError("--anchor-date must use YYYY-MM-DD.") from exc

    def _summary(self, counts):
        return ", ".join(f"{v} {k}" for k,v in sorted(counts.items()) if v) or "no records"

    def _delete(self, user):
        counts = Counter(contacts=Contact.objects.filter(user=user).count(),events=Event.objects.filter(user=user).count(),facts=Fact.objects.filter(contact__user=user).count(),observations=Observation.objects.filter(contact__user=user).count(),logs=Log.objects.filter(user=user).count(),reflections=Reflection.objects.filter(user=user).count())
        Reflection.objects.filter(user=user).delete(); Log.objects.filter(user=user).delete()
        Observation.objects.filter(contact__user=user).delete(); Fact.objects.filter(contact__user=user).delete()
        Event.objects.filter(user=user).delete(); Contact.objects.filter(user=user).delete()
        return counts

    def _populate(self, user, anchor):
        made=Counter(); categories=[]
        for name,icon in (("Preferences","FiHeart"),("Routines & goals","FiCompass"),("Work & school","FiBriefcase"),("Important dates","FiCalendar")):
            obj,new=FactCategory.objects.get_or_create(user=user,parent=None,name=name,defaults={"icon_reference":icon}); categories.append(obj); made["fact categories"]+=new
        markers=[]
        for name,color in (("General","#718096"),("Important","#E53E3E")):
            obj=ObservationMarker.objects.filter(name=name,is_system_default=True).first()
            if not obj:
                obj,new=ObservationMarker.objects.get_or_create(user=user,name=name,defaults={"color_hex":color,"icon_reference":"FiFileText"}); made["observation markers"]+=new
            markers.append(obj)
        contacts=self._contacts(user,anchor,categories,made)
        events=self._events(user,anchor,contacts,made)
        self._observations(contacts,events,markers,made)
        self._journals(user,events,made)
        self._media(user,made)
        return made

    def _contacts(self,user,anchor,categories,made):
        result=[]
        for i,s in enumerate(CONTACTS):
            first,last,email,phone,relation,company,pronouns,zone,job,study=s
            c=Contact.objects.create(user=user,first_name=first,last_name=last,preferred_name=first,email=email,phone_number=phone,address=f"{100+i} Demo Street, Starkville, MS 39759",relation=self._lookup(Relation,relation),company=company,pronouns=pronouns,birthday=date(1988+i,i%12+1,i*3%27+1),timezone=zone,first_met_date=anchor-timedelta(days=900-i*37),met_through="Work, family, or community",met_location="Starkville, MS")
            result.append(c); made["contacts"]+=1
            if i!=7:
                ContactMethod.objects.create(contact=c,kind="email",label="Primary email",value=email,is_primary=True)
                ContactMethod.objects.create(contact=c,kind="phone",label="Mobile",value=phone,is_primary=True)
                ContactAddress.objects.create(contact=c,label="Home",line_1=f"{100+i} Demo Street",city="Starkville",region="MS",postal_code="39759",country_code="US",is_primary=True)
            ContactEmployment.objects.create(contact=c,title=job,organization=company,is_current=True)
            ContactEducation.objects.create(contact=c,credential="Degree or certificate",field_of_study=study,institution="Regional University",is_current=False)
            for category,(label,value) in zip(categories,(("Favorite drink","Oat milk latte"),("Current goal","Monthly catch-up"),("Current focus","Project milestone"),("Important date","Next month"))):
                Fact.objects.create(contact=c,category=category,label=label,detail_value=f"{value} ({first})",is_conversation_cue=label in {"Favorite drink","Current goal"},pinned_at=timezone.now() if i==0 and label=="Favorite drink" else None); made["facts"]+=1
        return result

    def _events(self,user,anchor,contacts,made):
        result=[]; zone=timezone.get_current_timezone()
        for i,s in enumerate(EVENTS):
            title,offset,people,context,mode,mood,location,impact=s
            stamp=timezone.make_aware(datetime.combine(anchor+timedelta(days=offset),time(hour=9+i%10,minute=30 if i%2 else 0)),zone)
            event=Event.objects.create(user=user,title=f"Demo: {title}",description="Deterministic demo event.",event_timestamp=stamp,location_label=location,tier="milestone" if i in {2,4,27} else "routine",impact=impact,context_category=self._lookup(ContextCategory,context),interaction_mode=self._lookup(InteractionMode,mode),mood=self._lookup(Mood,mood))
            result.append(event); made["events"]+=1
            for p in people: EventParticipant.objects.create(event=event,contact=contacts[p]); made["participants"]+=1
        return result

    def _observations(self,contacts,events,markers,made):
        mapping={c.id:[] for c in contacts}
        for e in events:
            for p in e.participants.all(): mapping[p.contact_id].append(e)
        for c in contacts:
            for i,e in enumerate(mapping[c.id][:3]):
                Observation.objects.create(contact=c,marker=markers[i%2],body=f"{c.preferred_name}: demo observation {i+1}.",event=e,observation_type=("notice","conversation_cue","appreciation")[i],status=("current","revisit_later","archived")[i],occurred_at=e.event_timestamp,pinned_at=e.event_timestamp+timedelta(hours=1) if c==contacts[0] and i==0 else None); made["observations"]+=1

    def _journals(self,user,events,made):
        for i,fmt in enumerate((*COMPLETED,*DRAFTS)):
            event=events[i]; contact=event.participants.select_related("contact").first().contact
            model=Log if fmt in {"episode","social_energy","sentiment"} else Reflection
            completed=i<len(COMPLETED)
            j=model.objects.create(user=user,event=event,primary_contact=contact,title=f"Demo {fmt.replace('_',' ')} {i+1}",format=fmt,status="completed" if completed else "draft",occurred_at=event.event_timestamp,completed_at=event.event_timestamp+timedelta(hours=1) if completed else None,current_step="review" if completed else "writing",revision=1)
            made["logs" if model is Log else "reflections"]+=1
            if isinstance(j,Reflection): ReflectionContact.objects.create(reflection=j,contact=contact)
            self._detail(j,event)

    def _detail(self,j,event):
        if isinstance(j,Log) and j.format=="episode":
            d=EpisodeLogDetail.objects.create(log=j,category=EpisodeCategory.objects.filter(code="thought_pattern",is_system_default=True).first(),ended_at=event.event_timestamp+timedelta(minutes=35),is_ongoing=False)
            d.characteristics.set(EpisodeCharacteristic.objects.filter(code__in=["looping_thoughts","restless"],is_system_default=True)); d.context_tags.set(EpisodeContextTag.objects.filter(code="stressful_conversation",is_system_default=True))
        elif isinstance(j,Log) and j.format=="social_energy":
            d=SocialEnergyLogDetail.objects.create(log=j,before_state="open",battery_effect="reduced",mood_shift="improved",behavioral_effect="quieter",recovery_timing="later_day",interaction_context="small_group",group_size=3,familiarity="mixed",setting="structured")
            d.factors.set(SocialEnergyFactor.objects.filter(code="comfortable_setting",is_system_default=True))
        elif isinstance(j,Log) and j.format=="sentiment":
            d=SentimentLogDetail.objects.create(log=j,before_state=EmotionState.objects.filter(code="positive",is_system_default=True).first(),after_state=EmotionState.objects.filter(code="very_negative",is_system_default=True).first(),before_connection="close",after_connection="distant",initiated_by="mutual",overall_exchange="negative")
            d.dynamics.set(InteractionDynamic.objects.filter(code="guarded",is_system_default=True))
        elif isinstance(j,Reflection) and j.format=="interaction":
            InteractionReflectionDetail.objects.create(reflection=j,topic_or_activity="Planning a shared activity",user_actions="I offered two options.",contact_actions="They named a time.",contact_response="They stayed engaged.",user_response="I felt calmer.",feelings_now="Clear and connected.",important_to_understand="Specific options helped.")
        elif isinstance(j,Reflection) and j.format=="moment":
            MomentReflectionDetail.objects.create(reflection=j,focus_moment="A comfortable pause.",what_happened="We sat quietly.",noticed_around="Late light crossed the table.",response="I relaxed.",stood_out="The silence felt easy.",meaning_now="Comfort can be quiet.",remember="Leave room for pauses.")
        elif isinstance(j,Reflection) and j.format=="emotional":
            d=EmotionalReflectionDetail.objects.create(reflection=j,situation="A plan changed.",connected_factors="Predictability mattered.",communicating="I needed time.",understanding_now="I can ask for notice.")
            emotion=EmotionState.objects.filter(code="hurt",is_system_default=True).first()
            if emotion: d.emotions.add(emotion)
            EmotionalManifestation.objects.create(emotional_detail=d,kind="thought",display_order=0,text="I need a moment to reset.")
        elif isinstance(j,Reflection) and j.format=="free":
            FreeReflectionDetail.objects.create(reflection=j,body="Small, direct check-ins make it easier to stay connected.")

    def _media(self,user,made):
        asset=MediaAsset.objects.for_user(user).filter(original_filename__istartswith="demo-",content_type__istartswith="image/").first()
        if not asset: return
        free=Reflection.objects.filter(user=user,format="free").first(); emotional=Reflection.objects.filter(user=user,format="emotional").first()
        if free:
            a=ReflectionAttachment.objects.create(reflection=free,media_asset=asset,is_sensitive=False,display_order=0); free.cover_attachment=a; free.save(update_fields=["cover_attachment"]); made["reflection attachments"]+=1
        if emotional:
            ReflectionAttachment.objects.create(reflection=emotional,media_asset=asset,is_sensitive=True,display_order=0); made["reflection attachments"]+=1

    def _lookup(self,model,name):
        return model.objects.filter(name=name,is_system_default=True).first() if name else None
