"""High-level PS3 save folder helpers: decrypt/encrypt USR-DATA, rebuild PFD."""
import os
import shutil


def decrypt_save(save_dir, work_dir):
    """Decrypt a PS3 save folder into work_dir. Returns path to decrypted USR-DATA."""
    from roster_gen.ps3.pfd import PFD

    os.makedirs(work_dir, exist_ok=True)
    pfd = PFD(save_dir)
    for name in ("PARAM.SFO", "HED-DATA", "ICON0.PNG"):
        src = os.path.join(save_dir, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(work_dir, name))
    data = pfd.decrypt_file("USR-DATA")
    out = os.path.join(work_dir, "USR-DATA")
    with open(out, "wb") as f:
        f.write(data)
    with open(os.path.join(work_dir, ".pfd_src"), "w") as f:
        f.write(save_dir)
    return out, pfd


def encrypt_save(work_dir, out_dir, src_save_dir, sfo_source_dir=None, account_id=None):
    """Re-encrypt work_dir's USR-DATA and write a full save folder to out_dir.

    sfo_source_dir: optional path to a save folder whose PARAM.SFO (with the
    user's own account id) should be used as the template instead of src_save_dir.
    account_id: if given, overwrite ACCOUNT_ID in the SFO with this value.
    """
    from roster_gen.ps3.pfd import PFD

    os.makedirs(out_dir, exist_ok=True)
    sfo_src = sfo_source_dir if sfo_source_dir else src_save_dir
    # copy HED-DATA, ICON0 from src (binary files, unchanged)
    for name in ("HED-DATA", "ICON0.PNG"):
        src = os.path.join(src_save_dir, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(out_dir, name))
    # SFO from sfo_source (preserves the user's own account ID)
    sfo_src_path = os.path.join(sfo_src, "PARAM.SFO")
    if os.path.exists(sfo_src_path):
        shutil.copy2(sfo_src_path, os.path.join(out_dir, "PARAM.SFO"))
    # fix PARAM.SFO directory name only if renaming
    sfo_path = os.path.join(out_dir, "PARAM.SFO")
    if os.path.exists(sfo_path) and os.path.basename(out_dir) != os.path.basename(src_save_dir):
        folder_name = os.path.basename(out_dir)
        sub = folder_name.split("ROSTER-", 1)[-1] if "ROSTER-" in folder_name else folder_name
        from roster_gen.ps3.sfo import update_sfo_for_save
        update_sfo_for_save(sfo_path, folder_name, sub_title="ROSTER-" + sub,
                            account_id=account_id)
    # re-encrypt USR-DATA
    pfd = PFD(src_save_dir)
    with open(os.path.join(work_dir, "USR-DATA"), "rb") as f:
        plain = f.read()
    enc = pfd.encrypt_file("USR-DATA", plain)
    with open(os.path.join(out_dir, "USR-DATA"), "wb") as f:
        f.write(enc)
    # rebuild PFD: hashes are over the *encrypted* file bytes.
    file_data = {"USR-DATA": enc}
    pfd.rebuild(out_dir, file_data)
    return out_dir