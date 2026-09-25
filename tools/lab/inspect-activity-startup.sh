for id in 8 9 10 60 63 3; do
  echo "ACTIVITY $id"
  luna-send -t 1 -f -w 1200 luna://com.webos.service.activitymanager/getDetails "{\"activityId\":$id,\"current\":true,\"internal\":true}" 2>&1
done
cat /usr/share/luna-service2/client-permissions.d/com.webos.service.activitymanager.perm.json
cat /usr/share/luna-service2/roles.d/com.webos.service.activitymanager.role.json
ls /media/developer/usr/palm/services
ls /media/cryptofs/apps/usr/palm/services
cat /media/cryptofs/apps/usr/palm/services/org.jellyfin.webos.service/services.json
cat /media/cryptofs/apps/usr/palm/services/org.jellyfin.webos.service/package.json
ls /media/cryptofs/apps/usr/palm/services/org.jellyfin.webos.service
