import { NextRequest, NextResponse } from 'next/server';
import { getStoreClient } from '@/lib/apify';

export const dynamic = 'force-dynamic';

export async function POST(req: NextRequest) {
  try {
    const { active_list, list1_url, list2_url } = await req.json();
    const store = await getStoreClient();

    if (active_list) {
      await store.setRecord({ key: 'active_list', value: String(active_list) });
    }
    if (list1_url) {
      await store.setRecord({ key: 'list1_url', value: list1_url });
    }
    if (list2_url) {
      await store.setRecord({ key: 'list2_url', value: list2_url });
    }

    // Update custom_list_url for backward compatibility
    const [l1Rec, l2Rec, actRec] = await Promise.all([
      store.getRecord('list1_url'),
      store.getRecord('list2_url'),
      store.getRecord('active_list'),
    ]);
    const currentActive = String(actRec?.value || '1');
    const activeUrl = currentActive === '2' && l2Rec?.value ? l2Rec.value : l1Rec?.value;
    if (activeUrl) {
      await store.setRecord({ key: 'custom_list_url', value: activeUrl });
    }

    return NextResponse.json({ success: true, active_list: currentActive });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
