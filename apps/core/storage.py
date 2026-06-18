import cloudinary
import cloudinary.uploader
from django.core.files.storage import Storage


class CloudinaryImageStorage(Storage):
    """Minimal Cloudinary storage for user avatars/cover images.

    Uploads every file as a new Cloudinary resource with an auto-generated
    public ID.  The public ID is persisted in the database and used to
    reconstruct the URL on subsequent reads.
    """

    def _save(self, name, content):
        response = cloudinary.uploader.upload(content, resource_type='image')
        return response['public_id']

    def url(self, name):
        if not name:
            return ''
        # Old local/legacy paths contain '/' or a file extension.
        # Cloudinary auto-generated public_ids are pure hex (no '/', no '.').
        if '/' in name or '.' in name:
            return ''
        return cloudinary.CloudinaryResource(
            name, default_resource_type='image',
        ).url

    def delete(self, name):
        cloudinary.uploader.destroy(name)

    def exists(self, name):
        return False
