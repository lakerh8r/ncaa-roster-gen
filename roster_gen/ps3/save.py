"""High-level PS3 save folder helpers: decrypt/encrypt USR-DATA, rebuild PFD."""
import os
import shutil


def decrypt_save(save_dir, work_dir):
    """Decrypt a PS3 save folder into work_dir. Returns path to decrypted USR-DATA."""
    from roster_gen.ps3.pfd import PFD

    os.makedirs(work_dir, exist_ok=True)
    pfd = PFD(save_dir)
    # copy non-protected files verbatim
    for name in ("PARAM.SFO", "HED-DATA", "ICON0.PNG"):
        src = os.path.join(save_dir, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(work_dir, name))
    # decrypt USR-DATA
    data = pfd.decrypt_file("USR-DATA")
    out = os.path.join(work_dir, "USR-DATA")
    with open(out, "wb") as f:
        f.write(data)
    # write a marker
    with open(os.path.join(work_dir, ".pfd_src"), "w") as f:
        f.write(save_dir)
    return out, pfd


def encrypt_save(work_dir, out_dir, src_save_dir):
    """Re-encrypt work_dir's USR-DATA and write a full save folder to out_dir."""
    from roster_gen.ps3.pfd import PFD

    os.makedirs(out_dir, exist_ok=True)
    # copy template files (SFO, HED-DATA, ICON0) from src
    for name in ("PARAM.SFO", "HED-DATA", "ICON0.PNG"):
        src = os.path.join(src_save_dir, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(out_dir, name))
    # re-encrypt USR-DATA
    pfd = PFD(src_save_dir)
    with open(os.path.join(work_dir, "USR-DATA"), "rb") as f:
        plain = f.read()
    enc = pfd.encrypt_file("USR-DATA", plain)
    with open(os.path.join(out_dir, "USR-DATA"), "wb") as f:
        f.write(enc)
    # rebuild PFD: hashes are over the *encrypted* file bytes.
    # HED-DATA is left untouched (its on-disk size is padded; only its
    # logical 28 bytes are hashed, and they did not change).
    file_data = {"USR-DATA": enc}
    pfd.rebuild(out_dir, file_data)
    return out_dir