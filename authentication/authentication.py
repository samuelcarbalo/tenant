class EmailOrganizationBackend(ModelBackend):
    def authenticate(self, request, email=None, password=None, organization_slug=None, **kwargs):
        print(f"========== BACKEND AUTH ==========")
        print(f"Email: {email}")
        print(f"Org slug: {organization_slug}")
        
        if not email or not password or not organization_slug:
            print("Faltan datos")
            return None
            
        try:
            user = User.objects.get(
                email=email,
                organization__slug=organization_slug
            )
            print(f"Usuario encontrado: {user}")
            print(f"Password check: {user.check_password(password)}")
            if user.check_password(password):
                return user
        except User.DoesNotExist:
            print("Usuario no existe")
            return None
        return None