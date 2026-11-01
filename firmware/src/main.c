/* TuyaOpen-based LAN audio and language-style bridge. */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "tuya_cloud_types.h"
#include "tal_api.h"
#include "tal_network.h"
#include "tal_wifi.h"
#include "tal_kv.h"
#include "tal_cli.h"
#include "tkl_output.h"
#include "tdl_audio_manage.h"
#include "tdl_button_manage.h"
#include "board_com_api.h"
#include "lvgl.h"
#include "lv_vendor.h"
#include "cJSON.h"
#include "bridge_token.h"
#include "synkore_spin.h"

/* T5 platform API: vendor VAD otherwise stops PCM output after prolonged silence.
 * Push-button recording needs a continuous PCM stream, including quiet frames. */
extern void tkl_ai_disable_vendor_vad(void);

#define MAX_AUDIO (16000 * 2 * 20)
#define PORT 8765
LV_FONT_DECLARE(font_puhui_16_4);
static MUTEX_HANDLE guard;
static TDL_AUDIO_HANDLE_T audio;
static uint8_t *pcm;
static volatile uint32_t pcm_len, mic_frames, mic_peak;
static volatile int recording, request_start, request_stop, upload_ready, connect_wifi;
static volatile int client_fd = -1, authenticated;
static void set_note(const char *text);
static volatile int selected_style, selected_mode, live_running, request_cancel;
static volatile int ui_generation, pending_event, upload_busy;
static int result_page, result_pages=1;
static char teacher_options[400] = "暂无教师";
static char course_options[400] = "暂无课程";
static char teacher_ids[6][80], course_ids[6][80];
static int selected_teacher, selected_course;
static lv_obj_t *mode_btns[3], *ghost_image, *ghost_circle, *pet_label, *intro_layer;
static lv_obj_t *state_label, *meter, *context_dropdown;
static uint32_t pet_ticks, intro_ticks;
static volatile int remote_pet_state;
static void toggle_record(void)
{
    if (recording || live_running) { live_running = 0; request_stop = 1; }
    else if (!authenticated) set_note("请先连接电脑");
    else { live_running = selected_mode == 0; request_start = 1; }
}
static char result_text[4096] = "连接电脑后，点击录音或按 KEY。";
static char note[160] = "正在初始化";
static char wifi_ssid[33], wifi_password[65];
static lv_obj_t *status_label, *result_label, *record_label, *style_dropdown;
static lv_obj_t *settings, *ssid_field, *password_field, *keyboard;

static void set_note(const char *text)
{
    tal_mutex_lock(guard);
    snprintf(note, sizeof(note), "%s", text);
    tal_mutex_unlock(guard);
}

static int transfer(int fd, void *buf, uint32_t size, int send_data)
{
    uint32_t pos = 0;
    while (pos < size) {
        int n = send_data ? tal_net_send(fd, (uint8_t *)buf + pos, size - pos)
                          : tal_net_recv(fd, (uint8_t *)buf + pos, size - pos);
        if (n <= 0) return -1;
        pos += n;
    }
    return 0;
}

static int frame_send(int fd, uint8_t type, const void *data, uint32_t len)
{
    uint8_t head[12] = {'T','5','V','T',type,0,0,0,
        (uint8_t)(len >> 24), (uint8_t)(len >> 16), (uint8_t)(len >> 8), (uint8_t)len};
    if (transfer(fd, head, 12, 1)) return -1;
    return len ? transfer(fd, (void *)data, len, 1) : 0;
}

static int json_send(int fd, const char *text)
{
    return frame_send(fd, 1, text, strlen(text));
}

static void mic_cb(TDL_AUDIO_FRAME_FORMAT_E type, TDL_AUDIO_STATUS_E status, uint8_t *data, uint32_t len)
{
    (void)status;
    if (type != TDL_AUDIO_FRAME_FORMAT_PCM || !data) return;
    mic_frames++;
    uint32_t peak = 0;
    for (uint32_t i = 0; i + 1 < len; i += 2) {
        int16_t v = (int16_t)(data[i] | (data[i + 1] << 8));
        uint32_t amp = v < 0 ? -(int32_t)v : v;
        if (amp > peak) peak = amp;
    }
    mic_peak = peak;
    tal_mutex_lock(guard);
    if (recording && pcm) {
        uint32_t available = MAX_AUDIO - pcm_len;
        uint32_t copy = len < available ? len : available;
        memcpy(pcm + pcm_len, data, copy);
        pcm_len += copy;
        if (pcm_len >= (live_running ? 16000 * 2 * 6 : MAX_AUDIO)) request_stop = 1;
    }
    tal_mutex_unlock(guard);
}

static void record_action(lv_event_t *event)
{
    (void)event;
    if (selected_mode == 2) { pending_event = 3; set_note("已请求课后转译"); }
    else toggle_record();
}
static void key_event(char *name, TDL_BUTTON_TOUCH_EVENT_E event, void *arg)
{
    (void)name; (void)arg;
    if (event == TDL_BUTTON_LONG_PRESS_START) request_cancel = 1;
    else if (event == TDL_BUTTON_PRESS_SINGLE_CLICK) {
        if (selected_mode == 2) pending_event = 3;
        else toggle_record();
    }
    PR_NOTICE("SYNKORE KEY event=%d", event);
}

static void style_event(lv_event_t *event)
{
    selected_style = lv_dropdown_get_selected(lv_event_get_target(event));
}

static void field_focus(lv_event_t *event)
{
    lv_keyboard_set_textarea(keyboard, lv_event_get_target(event));
}

static void wifi_save(lv_event_t *event)
{
    (void)event;
    tal_mutex_lock(guard);
    snprintf(wifi_ssid, sizeof(wifi_ssid), "%s", lv_textarea_get_text(ssid_field));
    snprintf(wifi_password, sizeof(wifi_password), "%s", lv_textarea_get_text(password_field));
    tal_mutex_unlock(guard);
    connect_wifi = 1;
    lv_obj_add_flag(settings, LV_OBJ_FLAG_HIDDEN);
}

static lv_obj_t *make_button(lv_obj_t *parent, const char *text, int x, int y, int w, int h, lv_event_cb_t cb)
{
    lv_obj_t *b = lv_btn_create(parent);
    lv_obj_set_pos(b, x, y); lv_obj_set_size(b, w, h);
    if (cb) lv_obj_add_event_cb(b, cb, LV_EVENT_CLICKED, NULL);
    lv_obj_t *label = lv_label_create(b); lv_label_set_text(label, text); lv_obj_center(label);
    return b;
}

static void wifi_show(lv_event_t *event)
{
    (void)event;
    lv_obj_clear_flag(settings, LV_OBJ_FLAG_HIDDEN);
}

static void wifi_close(lv_event_t *event)
{
    (void)event;
    lv_obj_add_flag(settings, LV_OBJ_FLAG_HIDDEN);
}

static lv_obj_t *plain_label(lv_obj_t *parent, const char *text, int x, int y, int width)
{
    lv_obj_t *o=lv_label_create(parent); lv_label_set_text(o,text); lv_obj_set_pos(o,x,y);
    if(width) { lv_obj_set_width(o,width); lv_label_set_long_mode(o,LV_LABEL_LONG_WRAP); }
    return o;
}
static lv_obj_t *pet_overlay, *pet_sprite, *pet_state_text;
static unsigned pet_angles[2], pet_spin_left[2], pet_expression;
static int pet_open, pet_down_x[2], pet_down_angle[2], pet_dragged[2], pet_long[2];
static unsigned pet_temp_expression;
static uint32_t pet_temp_until, pet_tap_at[2];
static const char *pet_names[]={"陪伴","开心","眨眼","贴贴","思考","困困"};
static const char *pet_words[]={"我在这里，安静陪着你。","摸摸收到了。","给你一个小小的默契。","再靠近一点，贴贴。","让我慢慢想一想。","休息一会儿，轻触叫醒我。"};
static void spin_choose(unsigned channel,unsigned expression)
{
    if(channel==1) { pet_expression=expression%6;lv_label_set_text(pet_state_text,pet_words[pet_expression]); }
    else { pet_temp_expression=expression%6;pet_temp_until=lv_tick_get()+1800; }
}
static void spin_touch(lv_event_t *e)
{
    unsigned ch=(unsigned)(uintptr_t)lv_event_get_user_data(e);if(ch>1)return;
    lv_event_code_t code=lv_event_get_code(e);lv_indev_t *indev=lv_indev_get_act();lv_point_t p={0};
    if(indev)lv_indev_get_point(indev,&p);
    if(code==LV_EVENT_PRESSED) { pet_down_x[ch]=p.x;pet_down_angle[ch]=pet_angles[ch];pet_dragged[ch]=0;pet_long[ch]=0;pet_spin_left[ch]=0; }
    else if(code==LV_EVENT_PRESSING) {
        int dx=p.x-pet_down_x[ch];if(dx>10 || dx< -10) {
            pet_dragged[ch]=1;int angle=(pet_down_angle[ch]+dx/6)%24;
            pet_angles[ch]=(unsigned)(angle<0?angle+24:angle);
        }
    } else if(code==LV_EVENT_LONG_PRESSED && !pet_dragged[ch]) { pet_long[ch]=1;spin_choose(ch,3); }
    else if(code==LV_EVENT_CLICKED && !pet_dragged[ch] && !pet_long[ch]) {
        uint32_t now=lv_tick_get();unsigned expression=now-pet_tap_at[ch]<350?2:1;
        pet_tap_at[ch]=expression==2?0:now;spin_choose(ch,expression);
    }
}
static void spin_event(lv_event_t *e)
{
    unsigned ch=(unsigned)(uintptr_t)lv_event_get_user_data(e);if(ch<2)pet_spin_left[ch]=24;
}
static void pet_open_event(lv_event_t *e)
{
    (void)e;pet_open=1;pet_expression=0;pet_angles[1]=0;
    lv_obj_clear_flag(pet_overlay,LV_OBJ_FLAG_HIDDEN);lv_obj_move_foreground(pet_overlay);
    lv_label_set_text(pet_state_text,pet_words[0]);
}
static void pet_close_event(lv_event_t *e)
{
    (void)e;pet_open=0;pet_spin_left[1]=0;lv_obj_add_flag(pet_overlay,LV_OBJ_FLAG_HIDDEN);
}
static void pet_expression_event(lv_event_t *e)
{
    pet_expression=(unsigned)(uintptr_t)lv_event_get_user_data(e);if(pet_expression>5)pet_expression=0;
    lv_label_set_text(pet_state_text,pet_words[pet_expression]);
}
static void pet_mo_event(lv_event_t *e) { (void)e;spin_choose(1,1); }
static void spin_attach(lv_obj_t *object,unsigned channel)
{
    lv_obj_clear_flag(object,LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_event_cb(object,spin_touch,LV_EVENT_ALL,(void*)(uintptr_t)channel);
}
static void spin_modal_init(lv_obj_t *root)
{
    make_button(root,"互动",20,277,78,35,pet_open_event);
    lv_obj_t *spin=make_button(root,"转一圈",106,277,86,35,NULL);
    lv_obj_add_event_cb(spin,spin_event,LV_EVENT_CLICKED,(void*)(uintptr_t)0);
    pet_overlay=lv_obj_create(root);lv_obj_set_pos(pet_overlay,0,0);lv_obj_set_size(pet_overlay,480,320);
    lv_obj_set_style_bg_color(pet_overlay,lv_color_hex(0x282133),0);lv_obj_set_style_bg_opa(pet_overlay,LV_OPA_50,0);
    lv_obj_set_style_pad_all(pet_overlay,0,0);lv_obj_set_style_border_width(pet_overlay,0,0);lv_obj_clear_flag(pet_overlay,LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_t *panel=lv_obj_create(pet_overlay);lv_obj_set_pos(panel,18,18);lv_obj_set_size(panel,444,284);
    lv_obj_set_style_bg_color(panel,lv_color_hex(0xfaf6ef),0);lv_obj_set_style_border_width(panel,0,0);lv_obj_set_style_pad_all(panel,0,0);lv_obj_clear_flag(panel,LV_OBJ_FLAG_SCROLLABLE);
    plain_label(panel,"和 synkore 待一会儿",16,14,330);
    make_button(panel,"返回",360,4,70,38,pet_close_event);
    lv_obj_t *circle=lv_btn_create(panel);lv_obj_set_pos(circle,15,61);lv_obj_set_size(circle,160,160);
    lv_obj_set_style_radius(circle,LV_RADIUS_CIRCLE,0);lv_obj_set_style_bg_color(circle,lv_color_hex(0xe5dfef),0);
    lv_obj_set_style_pad_all(circle,0,0);lv_obj_set_style_shadow_width(circle,0,0);spin_attach(circle,1);
    pet_sprite=lv_img_create(circle);const lv_img_dsc_t *src=synkore_spin_frame(1,0,0);if(src)lv_img_set_src(pet_sprite,src);lv_obj_center(pet_sprite);lv_obj_add_flag(pet_sprite,LV_OBJ_FLAG_EVENT_BUBBLE);
    pet_state_text=plain_label(panel,pet_words[0],184,58,239);
    for(unsigned i=0;i<6;i++) {
        lv_obj_t *b=make_button(panel,pet_names[i],184+(i%3)*78,120+(i/3)*42,72,36,NULL);
        lv_obj_set_style_bg_color(b,lv_color_hex(0xe5def5),0);lv_obj_set_style_text_color(b,lv_color_hex(0x302c40),0);
        lv_obj_add_event_cb(b,pet_expression_event,LV_EVENT_CLICKED,(void*)(uintptr_t)i);
    }
    lv_obj_t *turn=make_button(panel,"转一圈",184,222,110,43,NULL);lv_obj_add_event_cb(turn,spin_event,LV_EVENT_CLICKED,(void*)(uintptr_t)1);
    make_button(panel,"摸摸",302,222,110,43,pet_mo_event);
    lv_obj_add_flag(pet_overlay,LV_OBJ_FLAG_HIDDEN);
}
static void spin_tick(void)
{
    for(unsigned ch=0;ch<2;ch++)if(pet_spin_left[ch]) { pet_angles[ch]=(pet_angles[ch]+1)%24;pet_spin_left[ch]--; }
    unsigned expression=remote_pet_state==1?4:remote_pet_state==2?1:remote_pet_state==3?5:0;
    if(recording)expression=0;
    else if(remote_pet_state!=1 && (int32_t)(pet_temp_until-lv_tick_get())>0)expression=pet_temp_expression;
    const lv_img_dsc_t *src=synkore_spin_frame(0,expression,pet_angles[0]);if(src)lv_img_set_src(ghost_image,src);
    if(pet_open) { src=synkore_spin_frame(1,pet_expression,pet_angles[1]);if(src)lv_img_set_src(pet_sprite,src); }
}

static void mode_event(lv_event_t *e)
{
    if(recording || upload_ready || live_running) { set_note("请先停止录音并等待上传"); return; }
    selected_mode=(int)(uintptr_t)lv_event_get_user_data(e); pending_event=1; ui_generation++;
}
static void context_event(lv_event_t *e)
{
    int v=lv_dropdown_get_selected(lv_event_get_target(e));
    if(selected_mode==1) { selected_teacher=v; pending_event=2; }
    else { selected_course=v; pending_event=6; }
}
static void cancel_event(lv_event_t *e) { (void)e; request_cancel=1; }
static void page_event(lv_event_t *e) { (void)e;result_page=(result_page+1)%result_pages;pending_event=5; }
static void ui_init(void)
{
    lv_disp_set_rotation(NULL,LV_DISP_ROT_270);
    PR_NOTICE("SYNKORE rotation=270 landscape=480x320");
    PR_NOTICE("SYNKORE spin_init=%d frames=24 expressions=6",synkore_spin_init());
    lv_obj_t *root=lv_scr_act(); lv_obj_set_style_text_font(root,&font_puhui_16_4,0);
    lv_obj_set_style_bg_color(root,lv_color_hex(0xfaf6ef),0); lv_obj_set_style_text_color(root,lv_color_hex(0x29283a),0);
    lv_obj_clear_flag(root,LV_OBJ_FLAG_SCROLLABLE);
    plain_label(root,"synkore",14,8,0);
    status_label=plain_label(root,"Wi-Fi 连接中",135,8,252);
    make_button(root,"Wi-Fi",398,2,76,32,wifi_show);
    const char *tabs[]={"实时听课","教师画像","课后转译"};
    for(int i=0;i<3;i++) { mode_btns[i]=make_button(root,tabs[i],12+i*155,41,148,39,NULL);
        lv_obj_set_style_bg_color(mode_btns[i],lv_color_hex(0xe5def5),0);
        lv_obj_set_style_text_color(mode_btns[i],lv_color_hex(0x302c40),0);
        lv_obj_add_event_cb(mode_btns[i],mode_event,LV_EVENT_CLICKED,(void*)(uintptr_t)i);
    }
    ghost_circle=lv_btn_create(root); lv_obj_set_pos(ghost_circle,14,91); lv_obj_set_size(ghost_circle,184,184);
    lv_obj_set_style_radius(ghost_circle,LV_RADIUS_CIRCLE,0); lv_obj_set_style_bg_color(ghost_circle,lv_color_hex(0xe5dfef),0);
    lv_obj_set_style_shadow_width(ghost_circle,0,0); lv_obj_set_style_border_width(ghost_circle,0,0);
    lv_obj_set_style_pad_all(ghost_circle,0,0); spin_attach(ghost_circle,0);
    ghost_image=lv_img_create(ghost_circle); const lv_img_dsc_t *initial=synkore_spin_frame(0,0,0);if(initial)lv_img_set_src(ghost_image,initial); lv_obj_center(ghost_image);
    lv_obj_add_flag(ghost_image,LV_OBJ_FLAG_EVENT_BUBBLE);
    pet_label=plain_label(root,"我准备好啦",37,278,160);lv_obj_add_flag(pet_label,LV_OBJ_FLAG_HIDDEN);
    style_dropdown=lv_dropdown_create(root); lv_obj_set_pos(style_dropdown,213,91); lv_obj_set_size(style_dropdown,170,35);
    lv_dropdown_set_options(style_dropdown,"正式\n易懂\n礼貌\n简洁");lv_obj_add_event_cb(style_dropdown,style_event,LV_EVENT_VALUE_CHANGED,NULL);
    context_dropdown=lv_dropdown_create(root); lv_obj_set_pos(context_dropdown,213,91);lv_obj_set_size(context_dropdown,250,35);
    lv_obj_set_width(context_dropdown,170);lv_dropdown_set_options(context_dropdown,"暂无教师");lv_obj_add_event_cb(context_dropdown,context_event,LV_EVENT_VALUE_CHANGED,NULL);lv_obj_add_flag(context_dropdown,LV_OBJ_FLAG_HIDDEN);
    make_button(root,"翻页",392,91,72,35,page_event);
    lv_obj_t *panel=lv_obj_create(root);lv_obj_set_pos(panel,210,133);lv_obj_set_size(panel,255,103);
    lv_obj_set_style_bg_opa(panel,LV_OPA_TRANSP,0);lv_obj_set_style_border_width(panel,0,0);lv_obj_set_style_pad_all(panel,2,0);
    result_label=plain_label(panel,"连接电脑后，按 KEY 开始。",0,0,245);
    lv_obj_t *btn=make_button(root,"开始听课",213,242,171,43,record_action);record_label=lv_obj_get_child(btn,0);
    lv_obj_set_style_bg_color(btn,lv_color_hex(0x373348),0);
    make_button(root,"取消",392,242,72,43,cancel_event);
    state_label=plain_label(root,"无声版 · KEY 开始/停止 · 长按取消",213,290,258);
    meter=lv_bar_create(root);lv_obj_set_pos(meter,215,121);lv_obj_set_size(meter,166,4);lv_bar_set_range(meter,0,32767);
    settings=lv_obj_create(root);lv_obj_set_pos(settings,0,0);lv_obj_set_size(settings,480,320);lv_obj_set_style_text_color(settings,lv_color_hex(0x29283a),0);
    plain_label(settings,"2.4GHz Wi-Fi",0,0,0);
    ssid_field=lv_textarea_create(settings);lv_obj_set_pos(ssid_field,0,26);lv_obj_set_size(ssid_field,215,41);lv_textarea_set_one_line(ssid_field,true);lv_textarea_set_max_length(ssid_field,32);lv_textarea_set_placeholder_text(ssid_field,"SSID");
    password_field=lv_textarea_create(settings);lv_obj_set_pos(password_field,224,26);lv_obj_set_size(password_field,215,41);lv_textarea_set_one_line(password_field,true);lv_textarea_set_password_mode(password_field,true);lv_textarea_set_max_length(password_field,64);lv_textarea_set_placeholder_text(password_field,"Password");
    make_button(settings,"连接",0,73,210,38,wifi_save);make_button(settings,"返回",225,73,210,38,wifi_close);
    keyboard=lv_keyboard_create(settings);lv_obj_set_pos(keyboard,-12,124);lv_obj_set_size(keyboard,465,167);lv_keyboard_set_textarea(keyboard,ssid_field);
    lv_obj_add_event_cb(ssid_field,field_focus,LV_EVENT_FOCUSED,NULL);lv_obj_add_event_cb(password_field,field_focus,LV_EVENT_FOCUSED,NULL);lv_obj_add_flag(settings,LV_OBJ_FLAG_HIDDEN);
    spin_modal_init(root);
    /* The intro covers the complete first framebuffer, before LVGL starts. */
    intro_layer=lv_obj_create(root);lv_obj_set_pos(intro_layer,0,0);lv_obj_set_size(intro_layer,480,320);lv_obj_set_style_bg_color(intro_layer,lv_color_hex(0xe5dfef),0);lv_obj_set_style_border_width(intro_layer,0,0);lv_obj_clear_flag(intro_layer,LV_OBJ_FLAG_SCROLLABLE);
    PR_NOTICE("SYNKORE UI %dx%d rotation=90 silent=1",lv_disp_get_hor_res(NULL),lv_disp_get_ver_res(NULL));
    lv_obj_t *im=lv_img_create(intro_layer);if(initial)lv_img_set_src(im,initial);lv_obj_align(im,LV_ALIGN_CENTER,0,-20);
    plain_label(intro_layer,"synkore",190,240,0);
    for(int i=0;i<12;i++) { lv_obj_t *dot=lv_obj_create(intro_layer);lv_obj_set_size(dot,4+i%3,4+i%3);lv_obj_set_pos(dot,20+(i*43)%420,15+(i*61)%210);lv_obj_set_style_radius(dot,LV_RADIUS_CIRCLE,0);lv_obj_set_style_bg_color(dot,lv_color_hex(i%2?0xf0b881:0xa397cb),0);lv_obj_set_style_border_width(dot,0,0); }
}

static void ui_task(void *arg)
{
    (void)arg;uint32_t ticks=0;int last_generation=-1;
    while(1) {
        if(request_cancel) { request_cancel=0;live_running=0;request_start=0;request_stop=0;
            tal_mutex_lock(guard);recording=0;upload_ready=0;pcm_len=0;tal_mutex_unlock(guard);
            pending_event=4;set_note("已取消"); }
        if(request_stop) { request_stop=0;tal_mutex_lock(guard);if(recording) { recording=0;upload_ready=pcm_len>0; }tal_mutex_unlock(guard);set_note(pcm_len?"录音完成，等待电脑接收":"已停止"); }
        if(request_start) { request_start=0;
            if(upload_ready || upload_busy) set_note("正在上传，请稍等");
            else if(!authenticated) { live_running=0;set_note("请先连接电脑"); }
            else if(!pcm || !audio) { live_running=0;set_note("音频初始化失败"); }
            else { tal_mutex_lock(guard);pcm_len=0;recording=1;tal_mutex_unlock(guard);remote_pet_state=0;set_note(selected_mode==1?"录制教师样本，按键结束":"正在听课，每6秒发送一段"); }
        }
        WF_STATION_STAT_E stat=WSS_IDLE;tal_wifi_station_get_status(&stat);NW_IP_S ip={0};if(stat==WSS_GOT_IP)tal_wifi_get_ip(WF_STATION,&ip);
        char line[100],local_note[160],local_result[4096];
        tal_mutex_lock(guard);snprintf(local_note,sizeof(local_note),"%s",note);snprintf(local_result,sizeof(local_result),"%s",result_text);tal_mutex_unlock(guard);
        snprintf(line,sizeof(line),"%s %s",ip.ip[0]?ip.ip:"Wi-Fi未连接",authenticated?"已连接":":8765");
        lv_vendor_disp_lock();
        if(intro_layer) { intro_ticks++;for(int i=2;i<14;i++) { lv_obj_t *dot=lv_obj_get_child(intro_layer,i);if(dot)lv_obj_set_y(dot,(intro_ticks*3+i*27)%230); } if(intro_ticks>=30) { lv_obj_del(intro_layer);intro_layer=NULL; } }
        lv_label_set_text(status_label,line);lv_label_set_text(result_label,local_result);
        lv_label_set_text(state_label,local_note);
        lv_label_set_text(record_label,selected_mode==2?"转译所选课程":recording||live_running?"停止并上传":selected_mode==1?"录制教师样本":"开始听课");
        lv_bar_set_value(meter,mic_peak,LV_ANIM_OFF);
        spin_tick();
        lv_obj_set_y(ghost_image,20+(ticks%20<10?ticks%10:9-ticks%10)/2);
        lv_label_set_text(pet_label,pet_ticks?"收到你的轻触啦":recording?"我在认真听":remote_pet_state==1?"让我想一想":remote_pet_state==2?"这段整理好了":"我准备好啦");if(pet_ticks)pet_ticks--;
        if(last_generation!=ui_generation) { last_generation=ui_generation;
            for(int i=0;i<3;i++)lv_obj_set_style_bg_color(mode_btns[i],lv_color_hex(i==selected_mode?0xe5def5:0xfaf6ef),0);
            if(selected_mode==0) { lv_obj_clear_flag(style_dropdown,LV_OBJ_FLAG_HIDDEN);lv_obj_add_flag(context_dropdown,LV_OBJ_FLAG_HIDDEN); }
            else { lv_obj_add_flag(style_dropdown,LV_OBJ_FLAG_HIDDEN);lv_obj_clear_flag(context_dropdown,LV_OBJ_FLAG_HIDDEN);lv_dropdown_set_options(context_dropdown,selected_mode==1?teacher_options:course_options);lv_dropdown_set_selected(context_dropdown,selected_mode==1?selected_teacher:selected_course); }
        }
        lv_vendor_disp_unlock();
        if(++ticks%50==0)PR_NOTICE("SYNKORE wifi=%d ip=%s mic_frames=%lu peak=%lu bytes=%lu rec=%d pc=%d mode=%d",stat,ip.ip,(unsigned long)mic_frames,(unsigned long)mic_peak,(unsigned long)pcm_len,recording,authenticated,selected_mode);
        tal_system_sleep(100);
    }
}

static const char *jstr(cJSON *object, const char *key)
{
    cJSON *v = cJSON_GetObjectItem(object, key);
    return cJSON_IsString(v) ? v->valuestring : "";
}

static int decode_hex(const char *input, char *output, size_t capacity)
{
    size_t len = strlen(input);
    if (len % 2 || len / 2 >= capacity) return -1;
    for (size_t i = 0; i < len; i += 2) {
        char pair[3] = {input[i], input[i + 1], 0};
        char *end = NULL;
        long v = strtol(pair, &end, 16);
        if (*end || v == 0) return -1;
        output[i / 2] = (char)v;
    }
    output[len / 2] = 0;
    return 0;
}

static void serial_wifi(int argc, char *argv[])
{
    if (argc != 3) { tal_cli_echo("BRIDGE_CONFIG_ERROR"); return; }
    char s[33], p[65];
    if (decode_hex(argv[1], s, sizeof(s)) || decode_hex(argv[2], p, sizeof(p))) {
        tal_cli_echo("BRIDGE_CONFIG_ERROR"); return;
    }
    tal_mutex_lock(guard);
    memcpy(wifi_ssid, s, strlen(s) + 1); memcpy(wifi_password, p, strlen(p) + 1);
    tal_mutex_unlock(guard);
    memset(p, 0, sizeof(p)); connect_wifi = 1;
    tal_cli_echo("BRIDGE_CONFIG_OK");
}

static const cli_cmd_t bridge_commands[] = {
    {.name="bridge_wifi", .help="Set Wi-Fi using hex UTF-8 SSID and password", .func=serial_wifi},
};

static int handle_frame(int fd)
{
    uint8_t h[12];
    if (transfer(fd, h, sizeof(h), 0) || memcmp(h, "T5VT", 4)) return -1;
    uint32_t len = ((uint32_t)h[8] << 24) | ((uint32_t)h[9] << 16) | ((uint32_t)h[10] << 8) | h[11];
    if (len > 8192 || h[4] != 1) return -1;
    char *data = tal_malloc(len + 1); if (!data) return -1;
    if (transfer(fd, data, len, 0)) { tal_free(data); return -1; } data[len] = 0;
    cJSON *j = cJSON_Parse(data); tal_free(data); if (!j) return -1;
    const char *op = jstr(j, "op");
    int rc = 0;
    if (!authenticated) {
        if (strcmp(op, "hello") || strcmp(jstr(j, "token"), BRIDGE_TOKEN)) rc = -1;
        else { authenticated = 1; rc = json_send(fd, "{\"op\":\"hello\",\"version\":\"2.2.0\",\"protocol\":1,\"capabilities\":[\"segmented_live\",\"teacher_select\",\"course_control\",\"pet_state\"],\"rate\":16000,\"max_seconds\":20}"); }
    } else if (!strcmp(op, "start")) { live_running = cJSON_IsTrue(cJSON_GetObjectItem(j,"continuous")); request_start = 1; }
    else if (!strcmp(op, "stop")) { live_running = 0; request_stop = 1; }
    else if (!strcmp(op, "style")) {
        cJSON *v = cJSON_GetObjectItem(j, "value");
        if (cJSON_IsNumber(v) && v->valueint >= 0 && v->valueint < 4) selected_style = v->valueint;
    } else if (!strcmp(op, "result")) {
        tal_mutex_lock(guard); snprintf(result_text, sizeof(result_text), "%s", jstr(j, "text")); tal_mutex_unlock(guard);
        cJSON *page=cJSON_GetObjectItem(j,"page"), *pages=cJSON_GetObjectItem(j,"total_pages");
        result_page=cJSON_IsNumber(page)?page->valueint:0;result_pages=cJSON_IsNumber(pages)?pages->valueint:1;
        if(result_pages<1)result_pages=1;
        set_note("已收到电脑回传文字");
        rc = json_send(fd, "{\"op\":\"result_ack\"}");
        PR_NOTICE("BRIDGE result received");
    } else if (!strcmp(op, "ping")) rc = json_send(fd, "{\"op\":\"pong\"}");
    else if (!strcmp(op, "cancel")) { request_cancel = 1; }
    else if (!strcmp(op, "mode")) {
        const char *v=jstr(j,"value"); selected_mode=!strcmp(v,"teacher")?1:!strcmp(v,"course")?2:0;
        live_running=0; request_stop=1; ui_generation++;
    } else if (!strcmp(op, "pet_state")) {
        const char *v=jstr(j,"value"); remote_pet_state=!strcmp(v,"thinking")?1:!strcmp(v,"success")?2:!strcmp(v,"rest")?3:0;
    } else if (!strcmp(op, "status") || !strcmp(op,"error")) { set_note(jstr(j,"message")); }
    else if (!strcmp(op, "progress")) {
        char p[150]; cJSON *v=cJSON_GetObjectItem(j,"percent");
        snprintf(p,sizeof(p),"%s %d%%",jstr(j,"stage"),cJSON_IsNumber(v)?v->valueint:0); set_note(p);
    } else if (!strcmp(op, "teacher_list") || !strcmp(op,"course_list")) {
        int teacher=!strcmp(op,"teacher_list"); char *options=teacher?teacher_options:course_options;
        char (*ids)[80]=teacher?teacher_ids:course_ids; options[0]=0; memset(ids,0,6*80);
        cJSON *items=cJSON_GetObjectItem(j,"items"), *item=NULL; int i=0;
        cJSON_ArrayForEach(item,items) { if(i>=6) break;
            const char *name=jstr(item,teacher?"name":"title");
            size_t used=strlen(options), available=400-used-1;
            if(strlen(name)>90 || strlen(name)+(i?1:0)>available) break;
            if(i) { strcat(options,"\n"); }
            strcat(options,name);
            snprintf(ids[i],80,"%s",jstr(item,"id"));i++;
        }
        if(!i) snprintf(options,400,"%s",teacher?"暂无教师":"暂无课程");
        int chosen=0;const char *selected=jstr(j,"selected_id");
        for(int n=0;n<i;n++)if(!strcmp(ids[n],selected))chosen=n;
        if(teacher) selected_teacher=chosen; else selected_course=chosen; ui_generation++;
    } else if (!strcmp(op,"get_catalog_state")) {
        cJSON *out=cJSON_CreateObject();cJSON_AddStringToObject(out,"op","catalog_state");
        cJSON_AddNumberToObject(out,"rotation",270);
        cJSON_AddStringToObject(out,"teacher_id",teacher_ids[selected_teacher]);
        cJSON_AddStringToObject(out,"course_id",course_ids[selected_course]);
        char *message=cJSON_PrintUnformatted(out);if(message){rc=json_send(fd,message);cJSON_free(message);}cJSON_Delete(out);
    } else if (!strcmp(op,"command_ack")) { /* Task completion is reported separately. */ }
    else rc=json_send(fd,"{\"op\":\"error\",\"code\":\"unsupported_op\"}");
    cJSON_Delete(j); return rc;
}

static void network_task(void *arg)
{
    (void)arg;
    int listener = -1;
    while (1) {
        if (connect_wifi) {
            connect_wifi = 0;
            char s[33], p[65];
            tal_mutex_lock(guard); memcpy(s, wifi_ssid, sizeof(s)); memcpy(p, wifi_password, sizeof(p)); tal_mutex_unlock(guard);
            cJSON *j = cJSON_CreateObject(); cJSON_AddStringToObject(j, "s", s); cJSON_AddStringToObject(j, "p", p);
            char *cfg = cJSON_PrintUnformatted(j);
            if (cfg && s[0]) { tal_kv_set("style_wifi", (uint8_t *)cfg, strlen(cfg) + 1);
                tal_wifi_station_disconnect(); tal_wifi_set_work_mode(WWM_STATION);
                tal_wifi_station_connect((int8_t *)s, (int8_t *)p); set_note("正在连接 Wi-Fi"); }
            if (cfg) cJSON_free(cfg);
            cJSON_Delete(j); memset(p, 0, sizeof(p));
        }
        WF_STATION_STAT_E stat = WSS_IDLE; tal_wifi_station_get_status(&stat);
        if (stat != WSS_GOT_IP) {
            if(client_fd>=0) { tal_net_close(client_fd);client_fd=-1;authenticated=0;live_running=0;request_stop=1; }
            if(listener>=0) { tal_net_close(listener);listener=-1; }
            tal_system_sleep(200); continue;
        }
        if (listener < 0) {
            listener = tal_net_socket_create(PROTOCOL_TCP);
            if (listener < 0 || tal_net_bind(listener, TY_IPADDR_ANY, PORT) || tal_net_listen(listener, 1)) {
                if (listener >= 0) tal_net_close(listener);
                listener = -1; tal_system_sleep(1000); continue;
            }
            set_note("等待电脑连接"); PR_NOTICE("BRIDGE TCP listening 8765");
        }
        int fd = client_fd >= 0 ? client_fd : listener;
        TUYA_FD_SET_T fds; TAL_FD_ZERO(&fds); TAL_FD_SET(fd, &fds);
        int ready = tal_net_select(fd + 1, &fds, NULL, NULL, 100);
        if (ready > 0) {
            if (client_fd < 0) {
                TUYA_IP_ADDR_T peer = 0; uint16_t port;
                client_fd = tal_net_accept(listener, &peer, &port); authenticated = 0;
                if (client_fd >= 0) { tal_net_set_timeout(client_fd, 3000, TRANS_RECV); tal_net_set_timeout(client_fd, 5000, TRANS_SEND); }
            } else if (handle_frame(client_fd)) {
                tal_net_close(client_fd); client_fd = -1; authenticated = 0; live_running=0; request_stop=1; set_note("电脑连接断开，可重新连接");
            }
        }
        if (authenticated && pending_event) {
            int event=pending_event; pending_event=0; cJSON *out=cJSON_CreateObject();
            if(event==1) { cJSON_AddStringToObject(out,"op","mode"); cJSON_AddStringToObject(out,"value",selected_mode==1?"teacher":selected_mode==2?"course":"live"); }
            else if(event==2) { cJSON_AddStringToObject(out,"op","teacher_select"); cJSON_AddStringToObject(out,"teacher_id",teacher_ids[selected_teacher]); }
            else if(event==3) { cJSON_AddStringToObject(out,"op","course_action"); cJSON_AddStringToObject(out,"job_id",course_ids[selected_course]); cJSON_AddStringToObject(out,"action","start"); }
            else if(event==6) { cJSON_AddStringToObject(out,"op","course_select"); cJSON_AddStringToObject(out,"course_id",course_ids[selected_course]); }
            else if(event==5) { cJSON_AddStringToObject(out,"op","get_result"); cJSON_AddNumberToObject(out,"page",result_page); }
            else { cJSON_AddStringToObject(out,"op","cancel"); }
            char *message=cJSON_PrintUnformatted(out); if(message) { json_send(client_fd,message); cJSON_free(message); } cJSON_Delete(out);
        }
        if (authenticated && upload_ready && !recording) {
            upload_busy=1; uint32_t sending_len=pcm_len;
            char info[256]; snprintf(info, sizeof(info), "{\"op\":\"audio\",\"rate\":16000,\"bytes\":%lu,\"style\":%d,\"mode\":\"%s\",\"teacher_index\":%d}", (unsigned long)sending_len, selected_style, selected_mode==1?"teacher":"live",selected_teacher);
            if (json_send(client_fd, info) || frame_send(client_fd, 2, pcm, sending_len) || json_send(client_fd, "{\"op\":\"audio_end\"}")) {
                tal_net_close(client_fd); client_fd = -1; authenticated = 0; live_running=0; request_stop=1; set_note("上传失败，重连后自动重试");
            } else { upload_ready = 0; if(live_running) request_start=1; set_note("录音已传到电脑"); PR_NOTICE("BRIDGE uploaded %lu bytes", (unsigned long)sending_len); }
            upload_busy=0;
        }
    }
}

static void app_main(void *arg)
{
    (void)arg;
    tal_log_init(TAL_LOG_LEVEL_NOTICE, 4096, (TAL_LOG_OUTPUT_CB)tkl_log_output);
    PR_NOTICE("SYNKORE firmware 2.2.0 silent landscape TUYA_T5AI_BOARD_LCD_35565");
    tal_mutex_create_init(&guard); tal_sw_timer_init(); tal_workq_init();
    tal_kv_init(&(tal_kv_cfg_t){.seed="vmlkasdh93dlvlcy", .key="dflfuap134ddlduq"});
    OPERATE_RET rc = board_register_hardware(); PR_NOTICE("BRIDGE board_init=%d", rc);
    pcm = tal_psram_malloc(MAX_AUDIO);
    tkl_ai_disable_vendor_vad();
    rc = tdl_audio_find(AUDIO_CODEC_NAME, &audio);
    if (rc == OPRT_OK) rc = tdl_audio_open(audio, mic_cb);
    PR_NOTICE("BRIDGE audio_open=%d buffer=%p", rc, pcm);
    if (rc != OPRT_OK) audio = NULL;
    TDL_BUTTON_HANDLE key; TDL_BUTTON_CFG_T bc = {.button_debounce_time=30, .button_repeat_valid_time=0, .long_start_valid_time=1500, .long_keep_timer=100};
    rc = tdl_button_create(BUTTON_NAME, &bc, &key); PR_NOTICE("BRIDGE key_init=%d", rc);
    if (rc == OPRT_OK) { tdl_button_event_register(key, TDL_BUTTON_PRESS_SINGLE_CLICK, key_event); tdl_button_event_register(key, TDL_BUTTON_LONG_PRESS_START, key_event); tdl_button_set_ready_flag(BUTTON_NAME, 1); }
    lv_vendor_init(DISPLAY_NAME); lv_vendor_disp_lock(); ui_init(); lv_vendor_disp_unlock(); lv_vendor_start(5, 8192);
    tal_wifi_init(NULL); tal_wifi_set_work_mode(WWM_STATION);
    tal_cli_init_with_uart(0);
    tal_cli_cmd_register(bridge_commands, 1);
    uint8_t *saved = NULL; size_t n = 0;
    /* Reuse only network settings already stored on this board; never log passwords. */
    if (tal_kv_get("style_wifi", &saved, &n) != OPRT_OK) tal_kv_get("netinfo", &saved, &n);
    if (saved && n) {
        char *copy = tal_malloc(n + 1);
        if (copy) { memcpy(copy, saved, n); copy[n] = 0; cJSON *j = cJSON_Parse(copy);
            if (j) { snprintf(wifi_ssid, sizeof(wifi_ssid), "%s", jstr(j,"s")); snprintf(wifi_password, sizeof(wifi_password), "%s", jstr(j,"p")); connect_wifi = wifi_ssid[0] != 0; cJSON_Delete(j); }
            tal_free(copy); }
        tal_kv_free(saved);
    }
    if (!connect_wifi) set_note("请点 Wi-Fi 配置网络");
    THREAD_HANDLE th;
    THREAD_CFG_T cfg = {.stackDepth=8192, .priority=THREAD_PRIO_2, .thrdname="bridge_net"};
    tal_thread_create_and_start(&th, NULL, NULL, network_task, NULL, &cfg);
    cfg.stackDepth=12288; cfg.thrdname="bridge_ui";
    tal_thread_create_and_start(&th, NULL, NULL, ui_task, NULL, &cfg);
}

void tuya_app_main(void)
{
    THREAD_HANDLE th;
    THREAD_CFG_T cfg = {.stackDepth=8192, .priority=THREAD_PRIO_1, .thrdname="bridge_main"};
    tal_thread_create_and_start(&th, NULL, NULL, app_main, NULL, &cfg);
}
